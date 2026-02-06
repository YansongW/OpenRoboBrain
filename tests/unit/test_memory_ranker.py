"""
MemoryRanker 类人记忆排序器单元测试

覆盖:
- 五大信号的独立计算
- 遗忘曲线衰减行为
- 间隔重复记忆强化
- 扩散激活亲和度
- 多信号融合排序
- Min-max 归一化
"""

import math
import time
import pytest

from orb.data.memory.memory_stream import MemoryObject, MemoryType, MemoryStream
from orb.data.memory.memory_ranker import (
    MemoryRanker,
    RankingWeights,
    SignalBreakdown,
    RankedMemory,
    create_memory_ranker,
)


# ============== 辅助函数 ==============

def make_memory(
    description: str = "test memory",
    importance: float = 5.0,
    access_count: int = 0,
    memory_strength: float = 1.0,
    embedding: list = None,
    created_hours_ago: float = 0,
    accessed_hours_ago: float = 0,
    memory_type: MemoryType = MemoryType.OBSERVATION,
    tags: list = None,
) -> MemoryObject:
    """快速创建测试记忆"""
    now = time.time()
    return MemoryObject(
        description=description,
        memory_type=memory_type,
        importance=importance,
        access_count=access_count,
        memory_strength=memory_strength,
        embedding=embedding,
        created_at=now - created_hours_ago * 3600,
        last_accessed_at=now - accessed_hours_ago * 3600,
        tags=tags or [],
    )


def simple_embedding(dim: int = 4, seed: float = 0.0) -> list:
    """生成简单的测试 embedding"""
    return [math.sin(seed + i) for i in range(dim)]


# ============== Signal 1: Recency 遗忘曲线 ==============

class TestRecencyScore:
    """遗忘曲线衰减测试"""

    def test_just_accessed_is_1(self):
        """刚刚访问过的记忆 recency 接近 1.0"""
        ranker = MemoryRanker()
        mem = make_memory(accessed_hours_ago=0)

        score = ranker.recency_score(mem)
        assert score >= 0.99

    def test_half_life_decay(self):
        """验证半衰期: S=1 时 24 小时后降至约 50%"""
        ranker = MemoryRanker()
        mem = make_memory(accessed_hours_ago=24, memory_strength=1.0)

        score = ranker.recency_score(mem)
        assert 0.45 <= score <= 0.55  # 约 50%

    def test_stronger_memory_decays_slower(self):
        """记忆强度越高，衰减越慢"""
        ranker = MemoryRanker()
        weak = make_memory(accessed_hours_ago=48, memory_strength=1.0)
        strong = make_memory(accessed_hours_ago=48, memory_strength=3.0)

        weak_score = ranker.recency_score(weak)
        strong_score = ranker.recency_score(strong)

        assert strong_score > weak_score

    def test_very_old_memory_nearly_zero(self):
        """非常旧的记忆接近 0"""
        ranker = MemoryRanker()
        mem = make_memory(accessed_hours_ago=720, memory_strength=1.0)  # 30 天

        score = ranker.recency_score(mem)
        assert score < 0.01

    def test_safety_memory_persists(self):
        """高记忆强度（安全记忆）衰减极慢"""
        ranker = MemoryRanker()
        # 安全事故: importance=10, strength=10 (多次回忆后)
        mem = make_memory(accessed_hours_ago=168, memory_strength=10.0)  # 7 天

        score = ranker.recency_score(mem)
        assert score > 0.5  # 7 天后仍然超过 50%


# ============== Signal 2: Importance ==============

class TestImportanceScore:
    """重要性评分测试"""

    def test_mundane_low_score(self):
        """日常琐事重要性低"""
        ranker = MemoryRanker()
        mem = make_memory(importance=2.0)

        score = ranker.importance_score(mem)
        assert score == 0.2

    def test_critical_high_score(self):
        """关键事件重要性高"""
        ranker = MemoryRanker()
        mem = make_memory(importance=9.0)

        score = ranker.importance_score(mem)
        assert score == 0.9

    def test_normalized_range(self):
        """确保归一化到 [0, 1]"""
        ranker = MemoryRanker()

        assert ranker.importance_score(make_memory(importance=0)) == 0.0
        assert ranker.importance_score(make_memory(importance=10)) == 1.0
        assert ranker.importance_score(make_memory(importance=15)) == 1.0  # 钳位


# ============== Signal 3: Relevance ==============

class TestRelevanceScore:
    """语义相关性测试"""

    def test_identical_vectors(self):
        """相同向量相关性为 1"""
        ranker = MemoryRanker()
        emb = [1.0, 0.0, 0.0, 0.0]
        mem = make_memory(embedding=emb)

        score = ranker.relevance_score(mem, emb)
        assert abs(score - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        """正交向量相关性为 0"""
        ranker = MemoryRanker()
        mem = make_memory(embedding=[1.0, 0.0, 0.0, 0.0])

        score = ranker.relevance_score(mem, [0.0, 1.0, 0.0, 0.0])
        assert abs(score) < 0.001

    def test_opposite_vectors(self):
        """反向向量相关性为 -1"""
        ranker = MemoryRanker()
        mem = make_memory(embedding=[1.0, 0.0])

        score = ranker.relevance_score(mem, [-1.0, 0.0])
        assert abs(score - (-1.0)) < 0.001

    def test_no_embedding_returns_zero(self):
        """无 embedding 时返回 0"""
        ranker = MemoryRanker()
        mem = make_memory(embedding=None)

        score = ranker.relevance_score(mem, [1.0, 0.0])
        assert score == 0.0


# ============== Signal 4: Frequency (X 算法对数缩放) ==============

class TestFrequencyScore:
    """访问频率测试"""

    def test_zero_access(self):
        """零次访问频率为 0"""
        ranker = MemoryRanker()
        mem = make_memory(access_count=0)

        score = ranker.frequency_score(mem, max_access_count=10)
        assert score == 0.0

    def test_max_access_is_one(self):
        """最大访问次数归一化为 1"""
        ranker = MemoryRanker()
        mem = make_memory(access_count=100)

        score = ranker.frequency_score(mem, max_access_count=100)
        assert abs(score - 1.0) < 0.001

    def test_logarithmic_scaling(self):
        """验证对数缩放: 早期访问价值高"""
        ranker = MemoryRanker()

        # 1 次 vs 2 次的差距 > 50 次 vs 51 次的差距
        score_1 = ranker.frequency_score(make_memory(access_count=1), max_access_count=100)
        score_2 = ranker.frequency_score(make_memory(access_count=2), max_access_count=100)
        score_50 = ranker.frequency_score(make_memory(access_count=50), max_access_count=100)
        score_51 = ranker.frequency_score(make_memory(access_count=51), max_access_count=100)

        diff_early = score_2 - score_1
        diff_late = score_51 - score_50

        assert diff_early > diff_late  # 对数缩放: 边际递减


# ============== Signal 5: Context Affinity (扩散激活) ==============

class TestContextAffinityScore:
    """扩散激活测试"""

    def test_no_recently_activated(self):
        """无最近激活记忆时返回 0"""
        ranker = MemoryRanker()
        mem = make_memory(embedding=[1.0, 0.0, 0.0, 0.0])

        score = ranker.context_affinity_score(mem, recently_activated=None)
        assert score == 0.0

    def test_related_activation_boosts(self):
        """相关记忆激活提升亲和度"""
        ranker = MemoryRanker()

        # 当前记忆: "厨房"
        kitchen = make_memory(description="厨房", embedding=[1.0, 0.0, 0.0, 0.0])

        # 最近激活: "做饭" (与厨房高度相关)
        cooking = make_memory(description="做饭", embedding=[0.9, 0.1, 0.0, 0.0])

        score = ranker.context_affinity_score(kitchen, recently_activated=[cooking])
        assert score > 0.8

    def test_unrelated_activation_low(self):
        """不相关记忆激活时亲和度低"""
        ranker = MemoryRanker()

        kitchen = make_memory(description="厨房", embedding=[1.0, 0.0, 0.0, 0.0])
        music = make_memory(description="音乐", embedding=[0.0, 0.0, 0.0, 1.0])

        score = ranker.context_affinity_score(kitchen, recently_activated=[music])
        assert score < 0.1

    def test_decay_by_activation_order(self):
        """越近激活的影响越大"""
        ranker = MemoryRanker()

        target = make_memory(embedding=[1.0, 0.0, 0.0, 0.0])

        recent = make_memory(embedding=[0.9, 0.1, 0.0, 0.0])   # 更相关
        older = make_memory(embedding=[0.5, 0.5, 0.0, 0.0])     # 较相关

        # recent 在前 (权重 0.5^0=1.0), older 在后 (权重 0.5^1=0.5)
        score_recent_first = ranker.context_affinity_score(
            target, recently_activated=[recent, older]
        )

        # older 在前, recent 在后
        score_older_first = ranker.context_affinity_score(
            target, recently_activated=[older, recent]
        )

        # recent_first 应该更高，因为更相关的记忆获得更高权重
        assert score_recent_first > score_older_first

    def test_self_excluded(self):
        """自身不参与扩散激活计算"""
        ranker = MemoryRanker()

        mem = make_memory(embedding=[1.0, 0.0, 0.0, 0.0])

        # 最近激活列表中只有自身
        score = ranker.context_affinity_score(mem, recently_activated=[mem])
        assert score == 0.0


# ============== 综合排序 ==============

class TestRank:
    """多信号融合排序测试"""

    def test_empty_candidates(self):
        """空候选列表返回空"""
        ranker = MemoryRanker()
        result = ranker.rank("test", [])
        assert result == []

    def test_rank_returns_ranked_memories(self):
        """排序返回 RankedMemory 列表"""
        ranker = MemoryRanker()
        candidates = [
            make_memory(description="记忆A", importance=8.0),
            make_memory(description="记忆B", importance=3.0),
        ]

        result = ranker.rank("test query", candidates)

        assert len(result) == 2
        assert all(isinstance(r, RankedMemory) for r in result)
        # 重要性高的排在前
        assert result[0].memory.description == "记忆A"

    def test_recency_dominates_when_weighted(self):
        """高 recency 权重时，近期记忆排前"""
        ranker = MemoryRanker(weights=RankingWeights(
            recency=5.0, importance=0.0, relevance=0.0, frequency=0.0, context_affinity=0.0,
        ))

        recent = make_memory(description="刚刚", accessed_hours_ago=0.1)
        old = make_memory(description="很久以前", accessed_hours_ago=100)

        result = ranker.rank("test", [old, recent])

        assert result[0].memory.description == "刚刚"

    def test_importance_dominates_when_weighted(self):
        """高 importance 权重时，重要记忆排前"""
        ranker = MemoryRanker(weights=RankingWeights(
            recency=0.0, importance=5.0, relevance=0.0, frequency=0.0, context_affinity=0.0,
        ))

        important = make_memory(description="重要", importance=9.0)
        trivial = make_memory(description="琐碎", importance=2.0)

        result = ranker.rank("test", [trivial, important])

        assert result[0].memory.description == "重要"

    def test_relevance_dominates_when_weighted(self):
        """高 relevance 权重时，语义相关的排前"""
        ranker = MemoryRanker(weights=RankingWeights(
            recency=0.0, importance=0.0, relevance=5.0, frequency=0.0, context_affinity=0.0,
        ))

        relevant = make_memory(description="厨房", embedding=[1.0, 0.0, 0.0, 0.0])
        irrelevant = make_memory(description="音乐", embedding=[0.0, 0.0, 0.0, 1.0])

        query_emb = [1.0, 0.0, 0.0, 0.0]

        result = ranker.rank("厨房", [irrelevant, relevant], query_embedding=query_emb)

        assert result[0].memory.description == "厨房"

    def test_top_k_truncation(self):
        """top_k 截断"""
        ranker = MemoryRanker()
        candidates = [make_memory(description=f"M{i}") for i in range(20)]

        result = ranker.rank("test", candidates, top_k=5)
        assert len(result) == 5

    def test_signal_breakdown_available(self):
        """每个结果包含信号分解"""
        ranker = MemoryRanker()
        candidates = [make_memory(description="test")]

        result = ranker.rank("test", candidates)

        assert len(result) == 1
        signals = result[0].signals
        assert isinstance(signals, SignalBreakdown)
        d = signals.to_dict()
        assert "recency" in d
        assert "importance" in d
        assert "relevance" in d
        assert "frequency" in d
        assert "context_affinity" in d


# ============== 间隔重复效应 ==============

class TestSpacedRepetition:
    """间隔重复记忆强化测试"""

    def test_access_increases_strength(self):
        """每次访问增强记忆强度"""
        mem = make_memory(memory_strength=1.0)
        initial_strength = mem.memory_strength

        mem.record_access()

        assert mem.memory_strength > initial_strength
        assert mem.access_count == 1

    def test_longer_gap_more_boost(self):
        """间隔越长，增强越大"""
        mem_short = make_memory(memory_strength=1.0)
        mem_short.last_accessed_at = time.time() - 60  # 1 分钟前
        mem_short.record_access()
        boost_short = mem_short.memory_strength - 1.0

        mem_long = make_memory(memory_strength=1.0)
        mem_long.last_accessed_at = time.time() - 86400  # 24 小时前
        mem_long.record_access()
        boost_long = mem_long.memory_strength - 1.0

        assert boost_long > boost_short


# ============== MemoryStream 集成 ==============

class TestMemoryStreamIntegration:
    """MemoryStream + MemoryRanker 集成测试"""

    def test_retrieve_updates_recently_activated(self):
        """检索记忆更新最近激活列表"""
        stream = MemoryStream(agent_id="test")
        mem = stream.create_and_add("厨房里有杯子", importance=7.0)

        stream.retrieve(mem.memory_id)

        assert len(stream.recently_activated) == 1
        assert stream.recently_activated[0].memory_id == mem.memory_id

    def test_rank_with_stream_memories(self):
        """使用 MemoryStream 的记忆进行排序"""
        stream = MemoryStream(agent_id="test")
        ranker = MemoryRanker()

        # 添加记忆
        stream.create_and_add("今天天气很好", importance=2.0)
        stream.create_and_add("用户喜欢喝咖啡", importance=7.0)
        stream.create_and_add("机器人撞到了桌子", importance=9.0,
                              tags=["safety"])

        candidates = stream.get_all()
        result = ranker.rank("安全记录", candidates)

        # 最重要的（安全事故）应该排前
        assert result[0].memory.description == "机器人撞到了桌子"


# ============== 便捷函数 ==============

class TestCreateMemoryRanker:
    """便捷函数测试"""

    def test_create_with_defaults(self):
        """默认创建"""
        ranker = create_memory_ranker()
        assert isinstance(ranker, MemoryRanker)

    def test_create_with_custom_weights(self):
        """自定义权重创建"""
        ranker = create_memory_ranker(weights={
            "recency": 2.0,
            "importance": 1.5,
            "relevance": 1.0,
            "frequency": 0.3,
            "context_affinity": 0.5,
        })
        assert ranker.weights.recency == 2.0
        assert ranker.weights.frequency == 0.3


# ============== 运行 ==============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
