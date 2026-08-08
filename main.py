import sqlite3
import time
import json
import logging
import signal
from datetime import datetime
from contextlib import contextmanager

# ====================== 配置区 ======================
CHECK_INTERVAL = 20  # 轮询间隔 秒
DB_FILE = "auto_ship.db"
LOG_FILE = "ship_log.log"
# 商品资源模板：goods_id: 发货文案
GOODS_MAP = {
    1: "百度网盘：https://pan.baidu.com/s/xxxx 提取码：1234 | Vue前端模板全套",
    2: "Python爬虫脚本合集，解压密码666666",
    3: "Excel自动化VBA宏工具包"
}
# ====================================================

# 初始化日志
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)
logger = logging.getLogger("auto_ship")

# 全局退出标记
RUN_FLAG = True
def signal_handler(signum, frame):
    global RUN_FLAG
    RUN_FLAG = False
    logger.info("收到停止信号，程序即将退出...")
    print("\n收到停止信号，等待当前轮询完成后退出...")

# 注册Ctrl+C退出监听
signal.signal(signal.SIGINT, signal_handler)

# 数据库上下文管理器，复用连接、自动关闭
@contextmanager
def get_db_conn():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")  # 开启WAL，解决并发锁问题
    cur = conn.cursor()
    try:
        yield conn, cur
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# 初始化数据表
def init_db():
    with get_db_conn() as (conn, cur):
        # 卡密池表
        cur.execute('''
        CREATE TABLE IF NOT EXISTS card_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goods_id INT,
            card_text TEXT,
            status INT DEFAULT 0, -- 0未售出 1已售出
            sell_time TEXT
        )
        ''')
        # 订单表
        cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            goods_id INT,
            buyer_id TEXT,
            status INT DEFAULT 0, -- 0待发货 1已发货
            create_time TEXT,
            ship_time TEXT
        )
        ''')
    logger.info("数据库初始化完成")

# 批量导入卡密
def add_card_batch(goods_id, card_list):
    with get_db_conn() as (conn, cur):
        insert_data = [(goods_id, card) for card in card_list]
        cur.executemany("INSERT INTO card_pool(goods_id, card_text) VALUES (?, ?)", insert_data)
    print(f"成功导入{len(card_list)}条卡密")
    logger.info(f"商品{goods_id}批量导入{len(card_list)}条卡密")

# 获取一条未核销卡密（行锁防止并发抢同一张卡密）
def get_one_card(goods_id):
    with get_db_conn() as (conn, cur):
        cur.execute('''
            SELECT id, card_text FROM card_pool
            WHERE goods_id=? AND status=0 LIMIT 1 FOR UPDATE
        ''', (goods_id,))
        res = cur.fetchone()
        if not res:
            return None
        cid, text = res
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute('''
            UPDATE card_pool SET status=1, sell_time=? WHERE id=?
        ''', (now, cid))
    return text

# 【核心替换点】真实订单API拉取，当前为模拟数据
def fetch_pending_orders():
    """
    真实业务替换此处：
    1. 闲鱼开放平台API requests.get() 获取待发货订单
    2. 微信小店/千牛API 拉取未发货订单列表
    返回格式：[{"order_id":"单号","goods_id":"商品ID","buyer_id":"买家标识","create_time":"下单时间"}]
    """
    mock_orders = [
        {"order_id": "DD20260809001", "goods_id": 1, "buyer_id": "买家001", "create_time": "2026-08-09 10:20:00"},
    ]
    return mock_orders

# 自动发货单处理
def ship_order(order):
    oid = order["order_id"]
    gid = order["goods_id"]
    bid = order["buyer_id"]
    create_time = order["create_time"]
    ship_content = ""

    # 卡密商品逻辑
    card = get_one_card(gid)
    if card:
        ship_content = f"您购买的卡密：{card}\n{GOODS_MAP[gid]}"
    else:
        ship_content = GOODS_MAP[gid]

    # ========== 对接私信发送接口 【必须自行实现】 ==========
    # 示例：闲鱼私信SDK / wechaty微信机器人 / 企业微信消息推送
    print(f"【自动发货成功】订单{oid} 买家{bid}")
    print(f"发货内容：\n{ship_content}\n")
    logger.info(f"发货完成 | 订单:{oid} 买家:{bid} 商品ID:{gid}")
    logger.info(f"发货内容:{ship_content}")
    # ======================================================

    # 更新订单为已发货
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_conn() as (conn, cur):
        cur.execute('''
            INSERT OR REPLACE INTO orders(order_id, goods_id, buyer_id, status, create_time, ship_time)
            VALUES (?, ?, ?, 1, ?, ?)
        ''', (oid, gid, bid, create_time, now))

# 主循环监听
def main_loop():
    print("===== 自动发货机器人启动 Ctrl+C 停止 =====")
    logger.info("自动发货机器人启动")
    while RUN_FLAG:
        try:
            pending_orders = fetch_pending_orders()
            for order in pending_orders:
                oid = order["order_id"]
                # 判断订单是否已发货，跳过重复订单
                with get_db_conn() as (conn, cur):
                    cur.execute("SELECT status FROM orders WHERE order_id=?", (oid,))
                    order_status = cur.fetchone()
                if order_status and order_status[0] == 1:
                    logger.debug(f"订单{oid}已发货，跳过")
                    continue
                ship_order(order)
        except Exception as e:
            err_msg = f"轮询捕获异常: {str(e)}"
            print(err_msg)
            logger.error(err_msg, exc_info=True)
        # 等待指定秒数
        for _ in range(CHECK_INTERVAL):
            if not RUN_FLAG:
                break
            time.sleep(1)
    print("机器人已安全退出！")
    logger.info("自动发货机器人正常停止")

if __name__ == "__main__":
    init_db()
    # 示例导入卡密，纯资源模板商品注释本行
    # add_card_batch(1, ["ABC123DEF456", "XYZ789AAA000"])
    main_loop()