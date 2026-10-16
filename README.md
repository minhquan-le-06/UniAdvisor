# UniAdvisor

**Trợ lý lập kế hoạch nguyện vọng đại học.** UniAdvisor helps Vietnamese grade-12 students choose what to study and
build their list of 15 nguyện vọng (ordered university wishes), for programs in Hà Nội and TP.HCM admitted by the
national THPT exam score.

**Live demo:** https://uniadvisor-demo-v2.streamlit.app/

## Features

| Page | What the student does |
|---|---|
| **Về em** | Enters exam scores (expected or real) for Toán, Ngữ văn and the two electives they chose, province, khu vực and đối tượng ưu tiên, budget, whether to study near home, a favourite school. |
| **Chọn ngành** | *Đã có ngành quan tâm*: searches ngành by name, nickname or abbreviation (CNTT, KHMT, accents optional) and compares up to six, one row each with details on demand. *Chưa xác định ngành*: answers 12 questions plus free text and gets five nhóm ngành, each explained with "Vì em chọn ...". Then picks up to two hướng học, each a main ngành with up to two close ngành. |
| **Danh sách nguyện vọng** | Gets three phương án of 15 wishes, **Đúng ngành nhất**, **Hợp sở thích nhất** (or **Hợp môn học nhất** without the questionnaire) and **Tiết kiệm nhất**, compared on a five-axis pentagon; chooses one and adjusts it with controls or a Vietnamese chat. Every wish shows its level (mơ ước, thử sức, vừa sức, an toàn), the student's score and the 2025 and 2026 cutoffs, tuition and city. |
| **Lưu kế hoạch** | Downloads the plan as a JSON file and opens it again later, for example after the exam with real scores. |

**Rules decide the list, AI helps the student.** The order of the wishes comes from fixed, testable rules: the
student's score per program (best exam combination plus priority points per Thông tư 06/2026/TT-BGDĐT), a level
against the two latest cutoffs, quotas per level, safe wishes at the bottom, and a chance of no admission kept at or
below 5% over 20,000 simulated cutoff years. Two small models run on the CPU inside the app: a suggester that maps
the questionnaire to nhóm ngành, and a classifier that turns a chat message into one of 28 request types. The saved
model covers the original 19 types; fixed local rules cover the nine new Part 4 data/scope questions until retraining.
Every text the student reads comes from fixed templates filled with real data; nothing is generated at run time.

**Privacy.** What the student enters stays in the browser session: it is not logged, stored or sent to any outside
service. The chat does not call an LLM or cloud API. The plan file goes straight to the student's device.
The web version (`docs/design/web.md`, not in the public repository) sends the plan to its own server with each call,
stores nothing there and logs no request.

## Run locally (Python 3.12)

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest httpx      # Windows: .venv\Scripts\python
.venv/bin/python -m pytest                                       # runs on a small fake database
```

The app reads a SQLite database, `data/uniadvisor.db` (about 29 MB), which is not in this repository (`data/README.md`).
On the first local launch, the app builds that default file from the checked-in pipeline inputs; this can take a little
longer than subsequent launches. With an already built database at another location:

```bash
UNIADVISOR_DB=/path/to/uniadvisor.db .venv/bin/python -m streamlit run app.py     # or put it at data/uniadvisor.db
```

## Repository layout

| Path | Contents |
|---|---|
| `app.py` | Streamlit entry point |
| `src/uniadvisor/api/` | The web API (FastAPI): stateless, the same planner and texts as JSON |
| `web/` | The web frontend (Vite, React, TypeScript) |
| `web_api.py`, `vercel.json` | The API's entry point and the configuration for Vercel (`docs/design/web.md`, Hosting) |
| `Dockerfile` | One container (frontend and API) for any Docker host |
| `src/uniadvisor/ui/` | The pages, session, plan file and every text the student reads |
| `src/uniadvisor/planner/` | List rules: scores, levels, the 15-wish strategy, chances, the three phương án and their pentagons |
| `src/uniadvisor/majors/` | The questionnaire, the nhóm ngành suggester and the free-text reader |
| `src/uniadvisor/chat/` | The chat: splitting a message, classifying it, extracting values, answers |
| `src/uniadvisor/data/` | Database schema and readers |
| `config/` | Admission rules per year (`config/rules/`), list settings, provinces, questionnaire, model settings |
| `models/` | The trained suggester and chat classifier, with their evaluation reports |
| `pipelines/` | Offline tools that build the database and train the models (`pipelines/README.md`); not used by the running app |
| `tests/` | The test suite (fake database; no real data needed) |

## Data and models

The database covers 159 universities (98 in Hà Nội, 61 in TP.HCM) and 3,880 programs, of which 3,829 (364 ngành)
have a ngành code, a cutoff and a known exam combination and can be placed in a list; tuition is known for about half
of them. Cutoffs come from public news sites and the universities' own documents, which take priority when they
differ. The models are trained on invented students and messages written by three open LLM families and tested on a
fourth family they never saw:

| Evaluation | Baseline | Model |
|---|---|---|
| Suggester, target nhóm ngành in the top 5 (held-out LLM family, 656 students) | 26.5% (data scores) | 43.4% |
| Suggester, hand-written behaviour cases | 28 / 31 | 31 / 31 |
| Chat classifier, macro-F1 (held-out LLM family, 1,361 messages) | 0.641 (keyword rules) | 0.881 |
| Chat classifier, accuracy on 190 messages judged by people | 0.921 | 0.926 |
| List rules, three phương án for 272 invented students | | every list keeps the chance of no admission at or below 5% from a total of 19 points |

Details: `models/suggester/report.md`, `models/message_classifier/report.md`, `pipelines/README.md`.

## Data sources and attribution

| Source | Used for | Terms |
|---|---|---|
| O*NET 31.0 Database, U.S. Department of Labor, Employment and Training Administration | Occupations, knowledge, interests, work context per ngành | CC BY 4.0. "This product includes information from the O*NET 31.0 Database by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA), used under the CC BY 4.0 license (https://www.onetcenter.org/license_db.html). UniAdvisor has modified the information (selection, translation to Vietnamese, aggregation per ngành). USDOL/ETA has not approved, endorsed, or tested these modifications." |
| O*NET Resource Center crosswalk, CIP 2020 to O*NET-SOC 2019 | ngành -> occupations | O*NET Resource Center |
| MOET catalog of ngành (Thông tư 09/2022/TT-BGDĐT) | ngành codes and names | Government document |
| Admission regulation (Thông tư 06/2026/TT-BGDĐT) | Priority points, minimum scores, 15 wishes | Government document |
| Programme list compiled by the team (schools, programmes, admission methods, exam combinations) | Programs in scope | Not redistributed |
| VnExpress, Tuyensinh247, VietNamNet | Published cutoffs (điểm chuẩn) 2025-2026 | Public pages; not redistributed |
| Universities' own documents (admission and tuition notices) | Cutoffs, ngành codes, tuition | Not redistributed |
| GSO (General Statistics Office) labour-force survey | National average income, shown as context only | Public statistics |
| Open LLMs (Qwen2.5-7B-Instruct, Aya Expanse 8B, Gemma 2 9B, SeaLLM-7B-v2) | Writing invented students and chat messages for training | Each model's own licence; the generated data is not redistributed |

## Roadmap

Testing with real students; tuition and graduate employment rates for every university; a retrain of the suggester
with more invented students; more nhóm ngành fact sheets; universities outside Hà Nội and TP.HCM.

## Tóm tắt (tiếng Việt)

UniAdvisor giúp học sinh lớp 12 chọn ngành và lập danh sách 15 nguyện vọng cho các chương trình đại học ở Hà Nội và
TP.HCM, xét bằng điểm thi tốt nghiệp THPT. Em đã có ngành quan tâm thì tìm và so sánh; chưa xác định ngành thì trả
lời 12 câu hỏi và nhận năm nhóm ngành gợi ý kèm lý do. Ứng dụng tính điểm xét tuyển của em cho từng chương trình, xếp
mức (mơ ước, thử sức, vừa sức, an toàn) theo điểm chuẩn 2025 và 2026, và đề xuất **ba phương án**: Đúng ngành nhất,
Hợp sở thích nhất (hoặc Hợp môn học nhất) và Tiết kiệm nhất, kèm biểu đồ ngũ giác để so sánh. Em chọn một phương án
rồi điều chỉnh bằng các nút hoặc khung chat, và tải kế hoạch về máy. Mọi câu chữ đều từ mẫu cố định với dữ liệu thật;
ứng dụng không lưu thông tin em nhập.

---

Built for the MLAI Hackathon 2026 (TMA track, Decision Intelligence Challenge). Code licence: MIT (`LICENSE`).
