"""Add the one compatibility field still needed by the frozen Spring UI."""
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
with engine.begin() as connection:
    columns = {column["name"] for column in inspect(connection).get_columns("total_sheet")}
    if "ts_check_time" not in columns:
        connection.execute(text(
            "ALTER TABLE total_sheet ADD COLUMN ts_check_time DATETIME NULL "
            "COMMENT '教师确认批阅时间' AFTER ts_hand"
        ))
        print("added total_sheet.ts_check_time")
    else:
        print("total_sheet.ts_check_time already exists")
