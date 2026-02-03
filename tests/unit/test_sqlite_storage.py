"""
SQLite 存储适配器单元测试
"""

import asyncio
import pytest
from pathlib import Path

from kaibrain.data.storage.relational import (
    SQLiteStorage,
    DatabaseConfig,
    QueryResult,
    Migration,
    MigrationManager,
    create_storage,
)


class TestDatabaseConfig:
    """数据库配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = DatabaseConfig()
        assert config.database == "kaibrain.db"
        assert config.pool_size == 5
        
    def test_memory_database(self):
        """测试内存数据库"""
        config = DatabaseConfig(database=":memory:")
        assert config.is_memory is True
        
    def test_connection_string(self):
        """测试连接字符串"""
        config = DatabaseConfig(database="test.db")
        assert config.get_connection_string() == "test.db"


class TestQueryResult:
    """查询结果测试"""
    
    def test_empty_result(self):
        """测试空结果"""
        result = QueryResult()
        assert bool(result) is False
        assert len(result) == 0
        assert result.first() is None
        assert result.scalar() is None
        
    def test_with_data(self):
        """测试有数据的结果"""
        result = QueryResult(
            rows=[{"id": 1, "name": "test"}],
            columns=["id", "name"],
            rowcount=1,
        )
        assert bool(result) is True
        assert len(result) == 1
        assert result.first() == {"id": 1, "name": "test"}
        assert result.scalar() == 1
        
    def test_iteration(self):
        """测试迭代"""
        result = QueryResult(
            rows=[{"id": 1}, {"id": 2}],
        )
        ids = [row["id"] for row in result]
        assert ids == [1, 2]


class TestSQLiteStorage:
    """SQLite 存储测试"""
    
    @pytest.fixture
    async def storage(self) -> SQLiteStorage:
        """创建内存数据库存储"""
        config = DatabaseConfig(database=":memory:")
        storage = SQLiteStorage(config)
        await storage.connect()
        yield storage
        await storage.disconnect()
        
    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        """测试连接和断开"""
        config = DatabaseConfig(database=":memory:")
        storage = SQLiteStorage(config)
        
        assert storage.connected is False
        await storage.connect()
        assert storage.connected is True
        await storage.disconnect()
        assert storage.connected is False
        
    @pytest.mark.asyncio
    async def test_create_table(self, storage: SQLiteStorage):
        """测试创建表"""
        await storage.create_table(
            "users",
            {
                "id": "INTEGER",
                "name": "TEXT",
                "email": "TEXT",
            },
            primary_key="id",
        )
        
        assert await storage.table_exists("users") is True
        assert await storage.table_exists("nonexistent") is False
        
    @pytest.mark.asyncio
    async def test_insert_and_select(self, storage: SQLiteStorage):
        """测试插入和查询"""
        await storage.create_table(
            "items",
            {"id": "INTEGER", "name": "TEXT", "value": "REAL"},
            primary_key="id",
        )
        
        # 插入
        row_id = await storage.insert("items", {"name": "item1", "value": 10.5})
        assert row_id > 0
        
        # 查询
        result = await storage.select("items", where="name = ?", params=("item1",))
        assert len(result) == 1
        assert result.first()["name"] == "item1"
        assert result.first()["value"] == 10.5
        
    @pytest.mark.asyncio
    async def test_insert_many(self, storage: SQLiteStorage):
        """测试批量插入"""
        await storage.create_table(
            "batch_items",
            {"id": "INTEGER", "name": "TEXT"},
            primary_key="id",
        )
        
        data = [{"name": f"item{i}"} for i in range(100)]
        count = await storage.insert_many("batch_items", data)
        
        assert count == 100
        
        total = await storage.count("batch_items")
        assert total == 100
        
    @pytest.mark.asyncio
    async def test_update(self, storage: SQLiteStorage):
        """测试更新"""
        await storage.create_table(
            "update_test",
            {"id": "INTEGER", "status": "TEXT"},
            primary_key="id",
        )
        
        await storage.insert("update_test", {"id": 1, "status": "pending"})
        
        affected = await storage.update(
            "update_test",
            {"status": "completed"},
            "id = ?",
            (1,),
        )
        
        assert affected == 1
        
        result = await storage.select("update_test", where="id = ?", params=(1,))
        assert result.first()["status"] == "completed"
        
    @pytest.mark.asyncio
    async def test_delete(self, storage: SQLiteStorage):
        """测试删除"""
        await storage.create_table(
            "delete_test",
            {"id": "INTEGER", "name": "TEXT"},
            primary_key="id",
        )
        
        await storage.insert("delete_test", {"id": 1, "name": "to_delete"})
        await storage.insert("delete_test", {"id": 2, "name": "to_keep"})
        
        deleted = await storage.delete("delete_test", "id = ?", (1,))
        assert deleted == 1
        
        remaining = await storage.count("delete_test")
        assert remaining == 1
        
    @pytest.mark.asyncio
    async def test_json_serialization(self, storage: SQLiteStorage):
        """测试 JSON 序列化"""
        await storage.create_table(
            "json_test",
            {"id": "INTEGER", "data": "TEXT"},
            primary_key="id",
        )
        
        data = {"nested": {"key": "value"}, "list": [1, 2, 3]}
        await storage.insert("json_test", {"id": 1, "data": data})
        
        result = await storage.select("json_test", where="id = ?", params=(1,))
        # JSON 被序列化为字符串存储
        assert '"nested"' in result.first()["data"]
        
    @pytest.mark.asyncio
    async def test_transaction_commit(self, storage: SQLiteStorage):
        """测试事务提交"""
        await storage.create_table(
            "tx_test",
            {"id": "INTEGER", "value": "TEXT"},
            primary_key="id",
        )
        
        async with storage.transaction():
            await storage.insert("tx_test", {"id": 1, "value": "first"})
            await storage.insert("tx_test", {"id": 2, "value": "second"})
        
        count = await storage.count("tx_test")
        assert count == 2
        
    @pytest.mark.asyncio
    async def test_select_with_order_and_limit(self, storage: SQLiteStorage):
        """测试排序和分页"""
        await storage.create_table(
            "paging_test",
            {"id": "INTEGER", "score": "INTEGER"},
            primary_key="id",
        )
        
        for i in range(10):
            await storage.insert("paging_test", {"score": i * 10})
        
        # 降序取前3个
        result = await storage.select(
            "paging_test",
            columns=["score"],
            order_by="score DESC",
            limit=3,
        )
        
        scores = [r["score"] for r in result]
        assert scores == [90, 80, 70]
        
        # 分页
        result = await storage.select(
            "paging_test",
            order_by="score ASC",
            limit=3,
            offset=3,
        )
        
        scores = [r["score"] for r in result]
        assert scores == [30, 40, 50]


class TestMigrationManager:
    """迁移管理器测试"""
    
    @pytest.fixture
    async def storage(self) -> SQLiteStorage:
        """创建内存数据库存储"""
        config = DatabaseConfig(database=":memory:")
        storage = SQLiteStorage(config)
        await storage.connect()
        yield storage
        await storage.disconnect()
        
    @pytest.mark.asyncio
    async def test_migration_up(self, storage: SQLiteStorage):
        """测试升级迁移"""
        manager = MigrationManager(storage)
        
        manager.register(Migration(
            version=1,
            name="create_users",
            up="CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)",
            down="DROP TABLE users",
        ))
        
        manager.register(Migration(
            version=2,
            name="add_email",
            up="ALTER TABLE users ADD COLUMN email TEXT",
            down="",  # SQLite 不支持 DROP COLUMN
        ))
        
        applied = await manager.migrate()
        
        assert len(applied) == 2
        assert await storage.table_exists("users") is True
        
        version = await manager.get_current_version()
        assert version == 2
        
    @pytest.mark.asyncio
    async def test_migration_to_specific_version(self, storage: SQLiteStorage):
        """测试迁移到指定版本"""
        manager = MigrationManager(storage)
        
        manager.register(Migration(
            version=1,
            name="v1",
            up="CREATE TABLE v1_table (id INTEGER)",
            down="DROP TABLE v1_table",
        ))
        
        manager.register(Migration(
            version=2,
            name="v2",
            up="CREATE TABLE v2_table (id INTEGER)",
            down="DROP TABLE v2_table",
        ))
        
        # 只迁移到版本 1
        applied = await manager.migrate(target_version=1)
        
        assert len(applied) == 1
        assert await storage.table_exists("v1_table") is True
        assert await storage.table_exists("v2_table") is False


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_create_storage(self):
        """测试 create_storage 函数"""
        storage = create_storage(database=":memory:", pool_size=3)
        
        assert storage._config.database == ":memory:"
        assert storage._config.pool_size == 3
