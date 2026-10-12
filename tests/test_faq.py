"""FAQ matcher: Persian normalization, matching, escalation, bursts."""

from __future__ import annotations

import pytest

from bale_platform.faq import FaqMatch, group_bursts, load_entries, match_faq, normalize
from bale_platform.store import StoredMessage


def test_normalize_unifies_arabic_letters_and_digits():
    assert normalize("كلاس ۳۸۰ يا ٣٨٠؟") == "کلاس 380 یا 380"
    assert normalize("می‌شه!!! 😀") == "می شه"
    assert normalize("آدرس") == "ادرس"
    assert normalize("😀🙏") == ""


@pytest.mark.parametrize(
    "text,entry",
    [
        ("آدرس سرور چیه؟", "minecraft_server"),
        ("چطوری وارد گیم شم", "minecraft_server"),
        ("قیمت کلاس‌ها چقدره؟", "price_terms"),
        ("لینک رو باز نمیکنه", "join_class_problem"),
        ("میگه ارتباط با اسکای روم برقرار نشد", "join_class_problem"),
        ("من نمی‌تونم وارد جلسه تعیین سطح بشم", "join_class_problem"),
        ("چطوری داخل کلاس باشم", "join_class_howto"),
        ("تکالیف نمیاره", "homework_where"),
        ("ترم جدید کی شروع میشه", "new_term_start"),
        ("کلاس دوشنبه ها دارید؟", "class_days"),
        ("این کد رو کجای سایت وارد کنم؟", "buy_class"),
        ("میخواستم پسرم پلی تاک ثبت نام کنم", "registration_start"),
        ("هر ترم چند جلسه است؟", "term_length"),
        ("پروفایلمو کامل کردم ولی هنوز هشدار میده", "profile_warning"),
        ("میخوام وقت تعیین سطح رزرو کنم", "level_test_booking"),
        ("هزینه و شرایط برگزاری کلاسها رو میفرمایید", "price_terms"),
        ("فاینال کی برگزار میشه؟", "final_exam"),
    ],
)
def test_matches_expected_entry(text, entry):
    m = match_faq(text)
    assert m.action == "suggest", (text, m)
    assert m.entry_id == entry, (text, m)
    assert m.answer


@pytest.mark.parametrize(
    "text",
    [
        "جبرانی نداشت",
        "میخوام انصراف بدم",
        "باقی شهریه رو نمیدم",
        "قیمت رو گفتید ولی کلاس جبرانی کی هست",  # price + dispute: dispute wins
    ],
)
def test_dispute_escalates_and_never_answers(text):
    m = match_faq(text)
    assert m.action == "escalate"
    assert m.answer == ""


@pytest.mark.parametrize("text", ["ممنون", "مرسی عزیزم", "باشه حتما 🌷", "🙏", "اوکی ممنون"])
def test_acknowledgements_need_no_reply(text):
    assert match_faq(text).action == "no_reply"


@pytest.mark.parametrize(
    "text",
    [
        "بچه هایی که آموزش زبان می بینن تکلیف نوشتاری اصلا ندارن؟",  # not "where is homework"
        "سطح من کی ثبت میشه",
        "امیر چند جلسه ازش مونده؟",
        "هزینه باقیمانده ترم تقدیم شما",  # a payment notice, not a price question
        "فاینال رو انجام داد",
    ],
)
def test_unknown_questions_are_left_to_humans(text):
    assert match_faq(text).action == "none"


def test_multiple_topics_lower_confidence():
    m = match_faq("قیمت چنده و آدرس سرور رو هم بفرستید")
    assert m.action == "suggest"
    assert m.confidence <= 0.5
    assert m.alternates


def test_entries_are_well_formed():
    entries = load_entries()
    ids = [e.id for e in entries]
    assert len(ids) == len(set(ids))
    for e in entries:
        if e.kind == "answer":
            assert e.answer and e.patterns, e.id
            assert e.risk in {"safe", "review"}
        if e.kind == "escalate":
            assert not e.answer and e.patterns, e.id


def _msg(chat, ms, direction, text):
    return StoredMessage(
        chat_id=chat,
        message_id=ms,
        sender_id="x",
        text=text,
        timestamp="t",
        date_ms=ms,
        direction=direction,
    )


def test_group_bursts_merges_close_incoming_and_splits_on_reply():
    msgs = [
        _msg("1", 1_000, "in", "سلام"),
        _msg("1", 5_000, "in", "قیمت چنده"),
        _msg("1", 9_000, "out", "سلام عزیزم"),
        _msg("1", 12_000, "in", "ممنون"),
        _msg("2", 2_000, "in", "سرور"),
    ]
    bursts = group_bursts(msgs)
    assert {t for _, _, t in bursts} == {"ممنون", "سرور", "سلام\nقیمت چنده"}
