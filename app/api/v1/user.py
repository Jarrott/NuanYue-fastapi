# -*- coding: utf-8 -*-
"""
Pedro-Core FastAPI 用户模块 (Async Version)
---------------------------------------------
✅ 异步 SQLAlchemy ORM 操作
✅ Redis 缓存 / RabbitMQ 延迟任务
✅ JWT 登录认证
✅ 支持会员开通、签到、邀请关系树
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Body
from fastapi.responses import FileResponse

from sqlalchemy import select
from firebase_admin import auth as firebase_auth, firestore
from firebase_admin.firestore import firestore as fstore
from sqlalchemy.util import await_only

from app.api.v1.model.shop_product import ShopProduct
from app.api.v1.model.user_address import UserAddress
from app.api.v1.services.cart_service import CartService
from app.api.v1.services.check_out_service import CheckoutService
from app.api.v1.services.fs.favorite_service import FavoriteServiceFS
from app.api.v1.services.order_state_service import OrderStateService
from app.api.v1.services.store.store_follow_service import FavoriteStoreService
from app.api.v1.services.store.store_review import StoreReviewService
from app.api.v1.services.store.store_visit_service import StoreVisitService
from app.api.v1.services.user_address_service import UserAddressService
from app.extension.google_tools.firestore import fs_service
from app.extension.network.network import get_client_ip, geo_lookup, calc_vpn_score
from app.pedro.enums import KYCStatus
from app.pedro.pedro_jwt import jwt_service, FirebaseAuthService

from app.api.v1.schema.response import (
    SuccessResponse,
    LoginSuccessResponse,
    GoogleLoginSuccessResponse,
    UserInformationResponse, GoogleUserInfo, DepositCreateResponse, ErrorResponse)
from app.api.v1.services.auth_service import AuthService
from app.api.v1.services.deposit_service import DepositService
from app.api.v1.services.user_service import UserService
from user_agents import parse

from app.extension.websocket.wss import websocket_manager
from app.pedro import UserGroup
# from PIL import Image, ImageDraw, ImageFont

from app.pedro.db import async_session_factory
from app.pedro.exception import UnAuthentication
from app.pedro.pedro_jwt import jwt_service, login_required, admin_required
from app.config.settings_manager import get_current_settings
from app.api.v1.schema.user import (
    UserRegisterSchema,
    LoginSchema,
    UserInformationSchema,
    OTCDepositSchema,
    UserAgentSchema,
    InformationUpdateSchema,
    RefreshTokenSchema,
    ForgotPasswordSendSchema,
    ForgotPasswordResetSchema,
    ResetPasswordSendSchema,
    UserKycSchema,
    ToggleSchema,
    KycDetailSchema,
    UserAddressCreateSchema, UserAddressUpdateSchema, AddCartSchema, UpdateCartSchema, CheckoutSchema,
    UserPayMethodSchema
)

from app.api.cms.model.user import User
from app.api.cms.model.user_group import UserGroup
from app.pedro.response import PedroResponse
from app.util.invite_services import assign_invite_code, bind_inviter_relation
from app.extension.google_tools.rtdb_message import rtdb_msg
from app.util.crypto import cipher

rp = APIRouter(prefix="/user", tags=["用户"])
settings = get_current_settings()


# ======================================================
# 🧩 注册新用户
# ======================================================
@rp.post("/register", name="用户注册", response_model=SuccessResponse)
async def register_user(payload: UserRegisterSchema):
    # 用户名唯一性校验
    if await UserService.get_by_username(payload.username):
        return SuccessResponse.fail(msg="用户重复!")

    await UserService.create_user_ar(
        phone=payload.phone,
        email=payload.email,
        username=payload.username,
        password=payload.password,
        inviter_code=payload.inviter_code,
        nickname=payload.nickname,
        country=payload.country,
        register_type=payload.register_type,
        group_ids=payload.group_ids,
    )
    return SuccessResponse.success(msg="注册成功!")


# ======================================================
# 🔐 登录并生成 Token
# ======================================================
@rp.post("/login", name="用户名登录", response_model=LoginSuccessResponse)
async def login(data: LoginSchema, request: Request):
    """
    用户登录并获取 Token
    """
    print(data.username)
    user = await UserService.get_by_username(data.username)

    if data.password_encrypted:
        data.password = cipher.decrypt(data.password)
    if not user:
        return PedroResponse.fail(code=10020, msg="用户不存在")
    if not await user.verify_password(data.password):
        return PedroResponse.fail(code=10030, msg="密码错误")

    tokens = await jwt_service.after_login_security(user, request, data)
    firebase_tokens = await FirebaseAuthService.create_custom_token(user.id)

    # 记录登录设备信息
    ua_string = request.headers.get("User-Agent", "")
    device_info = UserAgentSchema.from_ua(ua_string)

    await User.add_login_device(user.id, device_info.dict())

    return LoginSuccessResponse(**tokens, firebase_token=firebase_tokens)


@rp.post("/google/login", name="谷歌登陆", response_model=GoogleLoginSuccessResponse)
async def google_login(payload: dict, request: Request):
    g = AuthService.verify_google_token(payload.get("id_token"))
    user = await UserService.get_by_username(g["email"])
    # 记录登录设备信息
    ua_string = request.headers.get("User-Agent", "")
    device_info = UserAgentSchema.from_ua(ua_string)

    await User.add_login_device(user.id, device_info.dict())
    if not user:
        user = await UserService.create_user_ar(
            username=g["email"],
            email=g["email"],
            nickname=g["name"] or g["email"].split("@")[0],
            password=g["email"].split("@")[1],
            avatar=g["picture"],
            inviter_code=payload.get("inviter_code"),
            group_ids=payload.get("group_ids"),
        )
    tokens = await AuthService.create_tokens(user)

    # 谷歌登录
    user_info = GoogleUserInfo(
        uid=g["uid"],
        email=g["email"],
        name=g["name"],
        avatar=g["picture"],
    )

    return GoogleLoginSuccessResponse(**tokens, user=user_info)


@rp.post("/refresh", name="刷新 Access Token", response_model=LoginSuccessResponse)
async def refresh_token(json: RefreshTokenSchema):
    """
    使用 Refresh Token 刷新 Access Token
    """

    # 1️⃣ 校验 refresh token
    tokens = await jwt_service.verify_refresh_token(json.refresh_token)
    return LoginSuccessResponse(**tokens)


@rp.get("/information", name="个人详情",
        response_model=UserInformationResponse[UserInformationSchema],
        dependencies=[Depends(login_required)])
async def get_user_info(current_user: User = Depends(login_required)):
    return UserInformationResponse.success(
        msg="个人信息获取成功",
        data=UserInformationSchema.smart_load(current_user)
    )


@rp.put("/information", name="更新个人信息")
async def update_user_info(
        payload: InformationUpdateSchema,
        current_user=Depends(login_required)
):
    user = current_user
    data = payload.model_dump(exclude_none=True)

    # ✅ 特殊 avatar
    if "avatar" in data:
        data["_avatar"] = payload.avatar

    # ✅ extra 字段专门处理
    extra_fields = ("phone", "gender", "birthday")
    extra_data = {k: data.pop(k) for k in list(data.keys()) if k in extra_fields}

    # ✅ 先更新普通字段
    if data:
        await user.update(commit=True, **data)

    # ✅ 再更新 extra 字段
    if extra_data:
        await user.update_extra(extra_data)

    return PedroResponse.success(msg="用户信息更新成功")


@rp.get("/forgot/password/{email}", name="【重置密码】邮箱链接")
async def forgot_email(email: str):
    action_settings = firebase_auth.ActionCodeSettings(
        url=f"{settings.app.server_domain}/v1/user/reset/password",
        handle_code_in_app=True
    )

    auth = firebase_auth.generate_password_reset_link(email, action_settings)

    return auth


@rp.post("/forgot/password/send/code", name="【重置密码】手机验证码")
async def forgot_send_code(data: ForgotPasswordSendSchema):
    await UserService.send_reset_code(data.phone)
    return SuccessResponse.success(msg="验证码已发送")


@rp.post("/forgot/password/reset")
async def forgot_reset(data: ForgotPasswordResetSchema):
    await UserService.reset_password(data.email, data.code, data.new_password)
    return SuccessResponse.success(msg="密码重置成功")


@rp.get("/reset/password")
async def reset_password_html():
    file_path = settings.storage.h5_path + "/templates/h5/reset_password/index.html"
    return FileResponse(file_path)


@rp.post("/reset/password")
async def reset_password(request: Request, query: ResetPasswordSendSchema):
    print("-------------check")
    # try:
    #     email = auth.verify_password_reset_code(oobCode)
    #     auth.confirm_password_reset(oobCode, password)
    #
    #     # ✅ 同步更新你本地数据库密码
    #     await User.update_password_by_email(email, password)
    #
    #     return templates.TemplateResponse(
    #         "reset_success.html", {"request": request}
    #     )
    # except Exception as e:
    #     print(e)
    #     return templates.TemplateResponse(
    #         "reset_fail.html", {"request": request}
    #     )

    return True


@rp.get("/diagnose", name="检测用户是否开启VPN")
async def diagnose(request: Request, tz: str = Query(None)):
    ip = get_client_ip(request)
    intel = geo_lookup(ip)
    intel = calc_vpn_score(intel, request.headers.get("Accept-Language"), tz)
    return {
        "ip": ip,
        "country": intel.get("country"),
        "asn": intel.get("asn"),
        "org": intel.get("org"),
        "is_idc": intel["is_idc"],
        "vpn_score": intel["vpn_score"],  # >60 基本可视为 VPN/代理
        "reason": intel["reason"],
    }


@rp.post("/deposit/otc", name="充值方式", response_model=DepositCreateResponse)
async def submit_otc(payload: OTCDepositSchema, current_user=Depends(login_required)):
    key, deposit = await DepositService.submit_manual_order(
        user_id=current_user.id,
        amount=payload.amount,
        token=payload.token,
        proof=payload.proof_image
    )

    return DepositCreateResponse(order_number=deposit.order_no)


@rp.get("/kyc", name="KYC认证详情", response_model=PedroResponse[KycDetailSchema])
async def kyc_detail(user=Depends(login_required)):
    snap = await fs_service.get(f"users/{user.id}/kyc/info")
    return PedroResponse.success(snap, schema=KycDetailSchema)


@rp.post("/kyc", name="用户提交认证")
async def kyc_apply(data: UserKycSchema, user=Depends(login_required)):
    uid = str(user.uuid)
    snap = await fs_service.get(f"users/{uid}/kyc/info")
    if snap:
        return PedroResponse.fail(msg="申请已经提交。请勿重复提交审核")

    # ✅ 写入 Firestore
    await fs_service.safe_set(
        path=f"users/{uid}/kyc/info",
        data=data.model_dump(),
    )

    # ✅ 更新 PGSQL Extra（标记 KYC 提交）
    if data.status == KYCStatus.PENDING.value:
        await user.set_extra(kyc_status=False, kyc_submitted=True)

    return PedroResponse.success(msg="KYC验证已提交，请等待审核")


@rp.get("/address", name="用户地址列表", response_model=PedroResponse[UserAddressCreateSchema])
async def get_address_list(user: User = Depends(login_required)):
    uid = str(user.uuid)
    result = await UserAddressService.list_addresses(uid)
    return PedroResponse.success(result, schema=UserAddressCreateSchema)


@rp.get("/address/{address_id}", name="地址详情", response_model=PedroResponse[UserAddressCreateSchema])
async def get_address_detail(address_id: int, user: User = Depends(login_required)):
    uid = str(user.uuid)
    result = await UserAddressService.get_address_detail(uid, address_id)
    return SuccessResponse.success(result, schema=UserAddressCreateSchema)


@rp.post("/address", name="买家用户添加地址")
async def add_user_address(data: UserAddressCreateSchema, user: User = Depends(login_required)):
    uid = str(user.uuid)
    user = await UserAddressService.add_address(uid, data.model_dump())
    if not user:
        return SuccessResponse.fail(msg="地址添加失败")
    return SuccessResponse.success(msg="地址提交成功")


@rp.put("/address/{address_id}", name="买家更新地址")
async def update_address(address_id: int, data: UserAddressUpdateSchema, user: User = Depends(login_required)):
    uid = str(user.uuid)
    result = await UserAddressService.update_address(uid, address_id, data.model_dump())
    return SuccessResponse.success(result)


@rp.delete("/address/{address_id}", name="买家删除地址")
async def delete_address(address_id: int, user: User = Depends(login_required)):
    uid = str(user.uuid)
    address = await UserAddress.get(user_id=uid, id=address_id)
    if not address:
        return PedroResponse.fail(msg="没有该地址")
    await address.delete(commit=True)
    return PedroResponse.success(msg="地址删除成功")


@rp.patch("/address/{address_id}/default", name="买家设置默认地址")
async def set_default_address(address_id: int, user: User = Depends(login_required)):
    uid = str(user.uuid)
    await UserAddressService.set_default(uid, address_id)
    return PedroResponse.success(msg="已设为默认地址")


@rp.post("/toggle", name="喜欢的商品")
async def toggle_favorite(data: ToggleSchema, user=Depends(login_required)):
    product = await ShopProduct.get(id=data.product_id)

    if not product:
        return PedroResponse.fail(msg="没有找到数据")
    return await FavoriteServiceFS.toggle(user.id, product.to_dict())


@rp.get("/toggle/list", name="喜欢的商品列表")
async def get_favorites(user=Depends(login_required)):
    return await FavoriteServiceFS.list(user.id, limit=20)


@rp.post("/{store_id}/visit")
async def store_visit(store_id: str, user: User = Depends(login_required)):
    uid = str(user.uuid)
    store = await StoreVisitService.record_visit(uid, store_id)
    if not store:
        PedroResponse.fail(msg="浏览错误")
    return PedroResponse.success()


@rp.post("/{store_id}/favorite")
async def favorite_store(store_id: str, user: User = Depends(login_required)):
    uid = str(user.uuid)
    return await FavoriteStoreService.favorite(uid, store_id)


@rp.delete("/{store_id}/favorite")
async def unfavorite_store(store_id: str, user: User = Depends(login_required)):
    uid = str(user.uuid)
    return await FavoriteStoreService.unfavorite(uid, store_id)


@rp.get("/{store_id}/favorite")
async def is_favorite(store_id: str, user: User = Depends(login_required)):
    uid = str(user.uuid)
    return await FavoriteStoreService.is_favorited(uid, store_id)


@rp.get("/favorites")
async def list_favorite_stores(uid: str = Depends(login_required)):
    return await FavoriteStoreService.list_favorites(uid)

@rp.get("/orders/{order_id}",name="订单详情")
async def get_order_detail(order_id: int, user: User = Depends(login_required)):
    uid = str(user.uuid)
    result = await OrderStateService.get_order_detail(uid, order_id)
    return SuccessResponse.success(result)

@rp.post("/orders/{order_id}/pay", name="用户支付商品")
async def pay_order(data:UserPayMethodSchema,order_id: str, user: User = Depends(login_required)):
    uid = str(user.uuid)
    return SuccessResponse.success(await OrderStateService.pay(order_id, uid,method=data.method))


@rp.post("/orders/{order_id}/cancel", name="用户取消购买")
async def cancel_order(order_id: int, user: User = Depends(login_required)):
    return SuccessResponse.success(await OrderStateService.cancel(order_id, user.id))


@rp.post("/orders/{order_id}/ship")
async def ship_order(order_id: int, tracking_number: str):
    return SuccessResponse.success(await OrderStateService.ship(order_id, tracking_number))


@rp.post("/orders/{order_id}/complete", name="用户完成收货")
async def complete_order(order_id: int):
    return SuccessResponse.success(await OrderStateService.complete(order_id))


@rp.post("/cart/add", name="用户商品添加到购物车")
async def add_to_cart(data: AddCartSchema, user: User = Depends(login_required)):
    uid = str(user.uuid)
    result = await CartService.add_to_cart(uid, data.product_id, data.qty)
    return SuccessResponse.success(result)


@rp.post("/cart/checkout", name="结算购物车,生成账单")
async def cart_checkout(data: CheckoutSchema, user: User = Depends(login_required)):
    uid = str(user.uuid)
    result = await CheckoutService.checkout(uid, address_id=data.address_id)
    return SuccessResponse.success(result)


@rp.patch("/cart/update/{product_id}", name="更新购物车商品")
async def update_item(product_id: int, data: UpdateCartSchema, user: User = Depends(login_required)):
    uid = str(user.uuid)
    return SuccessResponse.success(await CartService.update_quantity(uid, product_id, data.qty))


@rp.delete("/cart/{product_id}")
async def remove_item(product_id: int, user: User = Depends(login_required)):
    uid = str(user.uuid)
    return SuccessResponse.success(await CartService.remove_item(uid, product_id))


@rp.delete("/cart/clear")
async def clear_cart(user: User = Depends(login_required)):
    uid = str(user.uuid)
    return SuccessResponse.success(await CartService.clear(uid))


@rp.get("/cart", name="查看购物车")
async def get_cart(user: User = Depends(login_required)):
    uid = str(user.uuid)
    return SuccessResponse.success(await CartService.get_cart(uid))


@rp.post("/add/review", name="用户发布评论")
async def add_review():
    await StoreReviewService.add_review(
        merchant_uid="264365076079841280",
        user_id="1001",
        rating=4.8,
        comment="发货速度很快，客服态度很好！",
        images=["https://cdn.qi-yue.vip/review1.jpg"],
        order_id=uuid.uuid4().hex,
    )
    return PedroResponse.success()
