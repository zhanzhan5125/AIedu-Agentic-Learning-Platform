from app.ai.tutor import _needs_learning_profile


def test_learning_profile_delegation_boundary():
    assert not _needs_learning_profile("C语言中的指针是什么？", None)
    assert not _needs_learning_profile("教材中在哪一页讲了指针？", None)
    assert _needs_learning_profile("我的薄弱知识点有哪些？", None)
    assert _needs_learning_profile("我在指针这里总是出错，弱在哪里？", None)
    assert _needs_learning_profile("结合我的情况制定复习计划", None)


def test_short_followup_inherits_personalized_context():
    memory = {"recent_messages": [
        {"role": "user", "content": "我在指针这里总是出错，帮我分析一下"},
        {"role": "assistant", "content": "我会结合你的学习画像分析。"},
    ]}

    assert _needs_learning_profile("具体呢？", memory)
    assert not _needs_learning_profile("具体呢？", {"recent_messages": [
        {"role": "user", "content": "请解释一下指针是什么"},
    ]})
