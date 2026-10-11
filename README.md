# UniAdvisor

A Streamlit app that helps Vietnamese grade-12 students with two decisions: **what to study** (a shortlist of 1-2
ngành / nhóm ngành) and **how to fill their 15 nguyện vọng** (ordered university wishes) so that their exam score
gets them in. Scope: programs taught in Hà Nội and TP.HCM, admission by the national THPT exam score.

MLAI Hackathon 2026, Phase 1 submission. Code licence: MIT (see `LICENSE`).

## How it works

1. **Step 1, what to study.** A student who knows picks ngành directly. A student who does not answers 12 short
   questions plus free text; a model suggests 3-5 nhóm ngành, each with the answers that point to it. Suggestions come
   from fixed "data scores" (O*NET interests, knowledge areas, work context, which subjects the group's programs admit
   with) plus small learned corrections (a conditional logit trained on LLM-written invented students, tested on an
   LLM family it never saw). Close ngành are proposed from shared occupations and knowledge.
2. **Step 2, the list.** Fixed rules, no model: the student's score for each program (best exam combination +
   priority points), a level against the 2025 and 2026 cutoffs (an toàn / vừa sức / thử sức / mơ ước), quotas per
   level, and an order in which the safe wishes sit at the bottom. Chances come from 20,000 simulated next-year
   cutoffs built from how real cutoffs moved between 2025 and 2026.
3. **Three recommended lists** ("phương án" in the app). The same rules with three different priorities for which program fills a slot:
   **Đúng ngành nhất** (the chosen ngành first), **Nghề nghiệp hứa hẹn** (best career fit; **Hợp môn học nhất**, the strongest
   subjects, for a student who skipped the questions) and **Tiết kiệm nhất** (cheapest within budget). Each list shows a
   pentagon of its expected outcome (subject fit, ambitious wish, right ngành, tuition, career) and must keep the
   chance of no admission at or below 5%. The student picks one and adjusts it with controls or a chat (a small local
   classifier turns a message into changes shown on one card before they apply).

All text the student sees comes from fixed templates filled with data; nothing is generated at run time. Nothing the
student enters is stored.

## Quick start (Python 3.12)

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"      # Windows: .venv\Scripts\python
.venv/bin/python -m pytest                        # the test suite
```

**The app needs the database** `data/build/uniadvisor.db` (SQLite, about 29 MB), which is **not in this repository**
(see "Data"). Reviewers can use the hosted demo: **[demo link]** (deployed from a private copy that holds the database). With the database file:

```bash
UNIADVISOR_DB=/path/to/uniadvisor.db .venv/bin/python -m streamlit run app.py     # or put it at data/build/uniadvisor.db
```

Without the database the app tries to build it from raw inputs that are not distributed, and stops.

## What is included

| Path | Contents |
|---|---|
| `app.py`, `src/uniadvisor/app/` | The Streamlit app |
| `src/uniadvisor/plan/` | List rules, chances, the three lists and pentagons |
| `src/uniadvisor/suggest/` | Step 1 questionnaire scores, the suggestion model, the free-text reader, data cleaning and the notebook builder |
| `src/uniadvisor/chat/` | Message splitting, classifier, value extraction, answers |
| `src/uniadvisor/facts/` | Per-ngành facts from O*NET, closeness of ngành, fact sheets |
| `src/uniadvisor/data/`, `src/uniadvisor/collect/` | Database schema and build; cutoff collectors |
| `config/` | Regulation facts per admission year (`config/rules/`), list settings, questionnaire, model settings |
| `models/suggester/` | The step 1 suggestion model (`model.json`, `weights.npz`) and its report |
| `models/message_classifier/` | The chat classifier (`model.joblib`) and its report |
| `models/text_reader/report.md` | The free-text reader's report |
| `notebooks/` | Kaggle notebooks that generated the training data (invented students, chat messages) with open LLMs |
| `data/inputs/onet_31_0/`, `data/inputs/unipilot/subject.csv` | Inputs the tests read |
| `data/chat/checks.csv` | The chat's check set: 190 test messages with the types people judged right |
| `tests/` | The test suite; it runs on a small fake database, not on the real data |

Code comments refer to sections of the project's design spec ("spec 4.3"), which is not part of this snapshot.

## Data

**Not included:** the database, the raw inputs it is built from (cutoff pages collected from the sites below and their
cached copies, the UniPilot export, schools' documents captured by hand, human-reviewed corrections), and the
LLM-generated training data. They took a long collection and cleaning effort and include third-party content whose
redistribution terms we could not verify. The build code is included: `python -m uniadvisor.data.build` rebuilds the
database when those inputs are present.

What the database holds (build of 2026-10-11, from `data/build/coverage.md` written by the build): 159 universities
(98 Hà Nội, 61 TP.HCM), 3,880 programs in scope, of which 3,829 (98.7%, 364 ngành) have a ngành code, a cutoff and a
known exam combination and can be placed in a list; tuition is known for 1,940 programs.

## Measured results

| Result | Value | Command (needs the database unless noted) |
|---|---|---|
| Test suite | 442 passed, 1 skipped (it needs the LLM review files, not published) | `python -m pytest` (no database needed) |
| List bench: 272 invented students (17 shortlists x totals 15-29 x 2 cities) | 210 lists reach 15 wishes; from a total of 23 points the mean chance of no admission is at most 0.02% | `python -m uniadvisor.plan.bench` -> `data/build/bench.md` |
| Three-list bench (the same 272 students x 3 lists) | every list meets the 5% no-admission floor from a total of 19; 98 of 102 lists at 17 | `python -m uniadvisor.plan.bench_lists` -> `data/build/bench_lists.md` |
| Suggestion model, held-out LLM family (SeaLLM-7B-v2, 656 students) | target group in the top 5: 43.4% (data scores alone 26.5%); 31/31 hand-written cases | `models/suggester/report.md`, written by `python -m uniadvisor.suggest.train` (needs the generated students) |
| Data scores alone (no learned model) | 28/31 hand-written cases; most frequent group in random answers' top 5: 16.7% | `python -m uniadvisor.suggest.checks` |
| Chat classifier, held-out LLM family after review (847 messages) | accuracy 0.969 (rule baseline 0.704) | `models/message_classifier/report.md`, written by `python -m uniadvisor.chat.train` (needs the generated messages) |

## Data sources and attribution

| Source | Used for | Terms |
|---|---|---|
| O*NET 31.0 Database, U.S. Department of Labor, Employment and Training Administration | Occupations, knowledge, interests, work context per ngành | CC BY 4.0. "This product includes information from the O*NET 31.0 Database by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA), used under the CC BY 4.0 license (https://www.onetcenter.org/license_db.html). UniAdvisor has modified the information (selection, translation to Vietnamese, aggregation per ngành). USDOL/ETA has not approved, endorsed, or tested these modifications." |
| O*NET Resource Center crosswalk, CIP 2020 to O*NET-SOC 2019 | ngành -> occupations | O*NET Resource Center; terms not separately verified |
| MOET catalog of ngành (Thông tư 09/2022/TT-BGDĐT) | ngành codes and names | Government document; reuse terms not verified |
| UniPilot export | Programs, admission methods, exam combinations | Not verified |
| VnExpress, Tuyensinh247, VietNamNet | Published cutoffs (điểm chuẩn) 2025-2026, tuition | Collected from public pages; terms not verified; not redistributed |
| Universities' own documents (admission notices, tuition notices) | Cutoffs, codes, tuition the sites miss | Not redistributed |
| GSO (General Statistics Office) labour-force survey press release, 2025-01-06 | National average income shown as context | Public statistics |
| Open LLMs (Qwen2.5-7B-Instruct, Aya Expanse 8B, Gemma 2 9B, SeaLLM-7B-v2) | Writing invented students and chat messages for training (the notebooks) | Each model's own licence; the generated data is not redistributed |

No salary reports are used.

## Status

**Done:** the database build, the list rules with chances, the three lists with pentagons, the app flow (search,
questionnaire, list view, controls, chat, plan file), step 1 facts and closeness, the step 1 suggestion model and the
free-text reader. **In progress:** more invented students from one more LLM family and a retrain of the suggestion
model; tuition (known for half of the programs) and university employment rates (none yet) from the universities'
own documents. **Planned:** more fact sheets
(75 of 379 ngành have one) and testing on real students' messages.

## Tóm tắt (tiếng Việt)

UniAdvisor giúp học sinh lớp 12 chọn ngành và lập danh sách 15 nguyện vọng cho các chương trình đại học ở Hà Nội và
TP.HCM, xét bằng điểm thi tốt nghiệp THPT. Bước 1: em đã biết ngành thì chọn thẳng; chưa biết thì trả lời 12 câu hỏi
và mô hình gợi ý 3-5 nhóm ngành kèm lý do. Bước 2: ứng dụng tính điểm của em cho từng chương trình, xếp mức (an toàn,
vừa sức, thử sức, mơ ước) theo điểm chuẩn 2025 và 2026, và đề xuất **ba phương án**: Đúng ngành nhất, Nghề nghiệp hứa hẹn
(hoặc Hợp môn học nhất) và Tiết kiệm nhất, mỗi phương án có biểu đồ năm cạnh về kết quả dự kiến và giữ khả năng trượt hết ở
mức không quá 5%. Em chọn một phương án rồi điều chỉnh bằng các nút hoặc khung chat. Mọi câu chữ đều từ mẫu cố định với
dữ liệu thật; ứng dụng không lưu thông tin em nhập.

Cơ sở dữ liệu (điểm chuẩn, học phí, mã ngành đã làm sạch) không có trong kho mã này; người chấm dùng bản demo trực
tuyến. Cài đặt và chạy kiểm thử: xem "Quick start" ở trên.
