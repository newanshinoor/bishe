# backend_fastapi/init_user.py
from sqlalchemy import create_engine, text


def init_user_table():
    # ⚠️ 请修改为你自己的 MySQL 账号和密码
    db_url = "mysql+pymysql://root:123456@localhost:3306/fruit_shop"
    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            # 删掉之前带 phone 的旧表，确保字段干净
            conn.execute(text("DROP TABLE IF EXISTS users;"))

            # 创建带有 email 字段的新 users 表
            create_table_sql = text("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """)
            conn.execute(create_table_sql)

            # 插入一个默认管理员账号 (密码: 123456)
            insert_admin_sql = text("""
            INSERT IGNORE INTO users (username, password_hash, email) 
            VALUES ('饶程', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'admin@fruitshop.com');
            """)
            conn.execute(insert_admin_sql)
            conn.commit()

        print("✅ 用户表 (users) 重建成功，已将手机号全面升级为邮箱绑定！")
    except Exception as e:
        print(f"❌ 建表失败: {e}")


if __name__ == '__main__':
    init_user_table()