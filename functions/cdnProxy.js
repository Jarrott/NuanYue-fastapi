import { onRequest } from "firebase-functions/v2/https";
import fetch from "node-fetch";
import mime from "mime-types"; // ⭐ 自动识别 Content-Type

const BUCKET = "ttte-a5dae.appspot.com";

export const cdnProxy = onRequest(async (req, res) => {
  try {
    let filePath = req.path.replace(/^\/+/, ""); // 去掉多余斜杠

    if (!filePath) {
      return res.status(400).json({ error: "Missing path" });
    }

    // 🔥 必须 encode，否则 Firebase 会 404
    const encoded = encodeURIComponent(filePath);

    const fileUrl = `https://firebasestorage.googleapis.com/v0/b/${BUCKET}/o/${encoded}?alt=media`;

    // 请求真实文件
    const response = await fetch(fileUrl);

    if (!response.ok) {
      return res.status(404).json({
        error: "File not found",
        path: fileUrl,
      });
    }

    // 自动识别文件类型（webp/jpg/png/json/pdf）
    const contentType = mime.lookup(filePath) || "application/octet-stream";

    // 设置 CDN 缓存策略
    res.set({
      "Content-Type": contentType,
      "Cache-Control": "public, max-age=31536000, immutable",
      "Access-Control-Allow-Origin": "*",
    });

    // Node 22 语法：替代 buffer()
    const arrayBuffer = await response.arrayBuffer();
    res.status(200).send(Buffer.from(arrayBuffer));

  } catch (err) {
    res.status(500).json({
      error: "proxy failed",
      details: err.message,
    });
  }
});
