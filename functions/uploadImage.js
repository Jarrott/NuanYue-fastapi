import { onRequest } from "firebase-functions/v2/https";
import admin from "firebase-admin";
import sharp from "sharp";
import { v4 as uuidv4 } from "uuid";

if (!admin.apps.length) admin.initializeApp();

const storage = admin.storage();
const db = admin.firestore();
const BUCKET = storage.bucket();
const CDN = "https://up-sap.qi-yue.vip"; // 你的 CDN 域名

// -------------------- Upload Image (Base64) --------------------
export const uploadImage = onRequest(async (req, res) => {
  res.set("Access-Control-Allow-Origin", "*");
  res.set("Access-Control-Allow-Methods", "POST,OPTIONS");
  res.set("Access-Control-Allow-Headers", "*");

  if (req.method === "OPTIONS") return res.status(204).send("");

  try {
    const user = req.headers["x-user-id"] || "anonymous";
    const file = req.body?.file;

    if (!file) return res.status(400).json({ error: "Missing base64 file" });

    // ---- Limit Upload Frequency: 1/sec ----
    const userRef = db.collection("upload_stats").doc(user);
    const userData = (await userRef.get()).data() || {};
    const now = Date.now();

    if (userData.last_upload && now - userData.last_upload < 1000) {
      return res.status(429).json({ error: "Too fast, retry later" });
    }

    // ---- Decode Base64 ----
    const base64 = file.includes(",") ? file.split(",")[1] : file;
    const buffer = Buffer.from(base64, "base64");

    // ---- Size Limit: 8MB ----
    const sizeMB = buffer.length / 1024 / 1024;
    if (sizeMB > 8) return res.status(413).json({ error: "File > 8MB blocked" });

    // ---- Generate Storage Path ----
    const id = uuidv4();
    const date = new Date();
    const folder = `uploads/${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}/${id}`;

    const originPath = `${folder}/origin.jpg`;
    const webpPath = `${folder}/image.webp`;
    const thumbPath = `${folder}/thumb.webp`;

    // ---- Save Origin ----
    await BUCKET.file(originPath).save(buffer, {
      metadata: { contentType: "image/jpeg" },
    });

    // ---- Create WebP ----
    const webpBuffer = await sharp(buffer).webp({ quality: 85 }).toBuffer();
    await BUCKET.file(webpPath).save(webpBuffer, {
      metadata: { contentType: "image/webp" },
    });

    // ---- Create Thumbnail ----
    const thumbBuffer = await sharp(buffer)
      .resize(350)
      .webp({ quality: 70 })
      .toBuffer();
    await BUCKET.file(thumbPath).save(thumbBuffer, {
      metadata: { contentType: "image/webp" },
    });

    // ---- Update Upload Stats ----
    await userRef.set(
      {
        last_upload: now,
        total: admin.firestore.FieldValue.increment(1),
        files: admin.firestore.FieldValue.arrayUnion({
          id,
          created: now,
          url: `${CDN}/${originPath}`,
        }),
      },
      { merge: true }
    );

    return res.json({
      id,
      sizeMB: sizeMB.toFixed(2),
      original: `${CDN}/${originPath}`,
      webp: `${CDN}/${webpPath}`,
      thumb: `${CDN}/${thumbPath}`,
    });
  } catch (err) {
    return res.status(500).json({ error: "Upload failed", detail: err.message });
  }
});

// -------------------- Delete Image (All Variants) --------------------
export const deleteImage = onRequest(async (req, res) => {
  res.set("Access-Control-Allow-Origin", "*");
  res.set("Access-Control-Allow-Methods", "DELETE,OPTIONS");
  res.set("Access-Control-Allow-Headers", "*");

  if (req.method === "OPTIONS") return res.status(204).send("");

  try {
    const id = req.query?.id;
    if (!id) return res.status(400).json({ error: "Missing id" });

    const [files] = await BUCKET.getFiles({ prefix: `uploads/` });

    const targets = files.filter(f => f.name.includes(id));

    if (!targets.length) return res.status(404).json({ error: "Not found" });

    await Promise.all(targets.map(f => f.delete()));

    return res.json({
      status: "success",
      deleted: targets.map(f => f.name),
    });
  } catch (err) {
    return res.status(500).json({ error: "Delete failed", detail: err.message });
  }
});
