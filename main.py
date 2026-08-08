import sqlite3
import time
import json
from datetime import datetime

# ====================== 配置区 ======================
CHECK_INTERVAL = 20  # 每20秒查一次订单
DB_FILE = "auto_ship.db"
# 商品库：商品ID -> 发货内容（网盘链接/源码下载地址）
GOODS_MAP = {
    1: "百度网盘：https://pan.baidu.com/s/xxxx 提取码：1234 | Vue前端模板全套",
    2: "Python爬虫脚本合集，解压密码666666",
    3: "Excel自动化VBA宏工具包"
}

# 哈哈哈哈哈哈哈哈11111111111112222222222222222222

# ====================================================

# 初始化数据库
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # 卡密表（卖激活码/CDK用，纯模板商品可不用）
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
    conn.commit()
    conn.close()

# 添加批量卡密（一次性导入）
def add_card_batch(goods_id, card_list):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    for c in card_list:
        cur.execute("INSERT INTO card_pool(goods_id, card_text) VALUES (?, ?)", (goods_id, c))
    conn.commit()
    conn.close()
    print(f"成功导入{len(card_list)}条卡密")

# 获取一条未使用卡密
def get_one_card(goods_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
        SELECT id, card_text FROM card_pool
        WHERE goods_id=? AND status=0 LIMIT 1 FOR UPDATE
    ''', (goods_id,))
    res = cur.fetchone()
    if not res:
        conn.close()
        return None
    cid, text = res
    # 标记已售出
    cur.execute('''
        UPDATE card_pool SET status=1, sell_time=? WHERE id=?
    ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), cid))
    conn.commit()
    conn.close()
    return text

# 模拟获取待发货订单（真实场景替换为闲鱼/千牛API请求）
def fetch_pending_orders():
    # 这里写平台接口逻辑：轮询获取"待发货"订单
    # 示例模拟订单，实际调用requests拉取订单列表
    mock_orders = [
        {"order_id": "DD20260809001", "goods_id": 1, "buyer_id": "买家001"},
    ]
    return mock_orders

# 自动发货核心逻辑
def ship_order(order):
    oid = order["order_id"]
    gid = order["goods_id"]
    bid = order["buyer_id"]
    ship_content = ""

    # 判断是卡密商品 还是固定链接模板商品
    card = get_one_card(gid)
    if card:
        ship_content = f"您购买的卡密：{card}\n{GOODS_MAP[gid]}"
    else:
        ship_content = GOODS_MAP[gid]

    # ========== 这里对接发送消息接口 ==========
    # 1.闲鱼：调用闲鱼私信API发送 ship_content
    # 2.私域微信：wechaty/itchat发送消息给买家
    print(f"【自动发货成功】订单{oid} 买家{bid}")
    print(f"发货内容：\n{ship_content}\n")
    # ==========================================

    # 更新订单为已发货
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute('''
        INSERT OR REPLACE INTO orders(order_id, goods_id, buyer_id, status, create_time, ship_time)
        VALUES (?, ?, ?, 1, ?, ?)
    ''', (oid, gid, bid, now, now))
    conn.commit()
    conn.close()

# 主循环7*24小时监听
def main_loop():
    print("自动发货机器人启动...")
    while True:
        try:
            pending = fetch_pending_orders()
            for order in pending:
                # 查询订单是否已发货，避免重复
                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                cur.execute("SELECT status FROM orders WHERE order_id=?", (order["order_id"],))
                od = cur.fetchone()
                conn.close()
                if od and od[0] == 1:
                    continue
                ship_order(order)
        except Exception as e:
            print(f"轮询异常：{str(e)}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    init_db()
    # 示例：给商品1导入卡密，不卖卡密可注释
    # add_card_batch(1, ["ABC123DEF456", "XYZ789AAA000"])
    main_loop()