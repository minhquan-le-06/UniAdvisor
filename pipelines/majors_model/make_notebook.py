"""Write pipelines/notebooks/student_generation.ipynb: the Kaggle notebook in which open LLMs write invented students who answer
the questionnaire, for training the suggestion model. It runs on Kaggle (2x T4); this repository
never does.

The notebook embeds the questionnaire (config/questionnaire.yaml), the target nhóm ngành with their display names and
ngành, and the exam subjects, so it needs no other input. No real student's data is involved.

Run: python -m pipelines.majors_model.make_notebook
"""

from __future__ import annotations

import json
from pprint import pformat

from uniadvisor.ui.service import AppData
from pipelines.chat_model.make_notebook import GENERATE as CHAT_GENERATE, LIBS, _cell
from uniadvisor.paths import ROOT
from uniadvisor.majors.questions import load_questionnaire

OUT = ROOT / "pipelines" / "notebooks" / "student_generation.ipynb"
MAX_NGANH_SHOWN = 8

# Loading a model and building its chat prompt: the same code as the chat notebook (same families, same T4 setup).
MODEL_HELPERS = CHAT_GENERATE[CHAT_GENERATE.index("def load("):CHAT_GENERATE.index("def run_family(")]

INTRO = r"""# UniAdvisor: invented students for training the suggestion model ("Chưa xác định ngành")

Open LLMs write invented grade-12 students who answer the questionnaire (12 questions with fixed options, expected
exam scores, and the free text "Kể thêm về em"). Each prompt names one target **nhóm ngành**, so the label is known by
construction and the groups stay balanced.

**Method (cited, verified 2026-10-08)**
- Prompting off-the-shelf LLMs with a target label to generate labelled training data: Sahu et al. 2022, *Data
  Augmentation for Intent Classification with Off-the-shelf Large Language Models*, 4th Workshop on NLP for
  Conversational AI (ACL 2022), pp. 47-57.
- Attributed prompts (each prompt samples how sure the student is, which questions they skip, how many options they
  tick, writing style, whether their best subjects point elsewhere) for diversity and less bias: Yu et al. 2023,
  *Large Language Model as Attributed Training Data Generator: A Tale of Diversity and Bias*, NeurIPS 2023 Datasets and
  Benchmarks.
- A short persona per prompt, so students of one group differ: Chan et al. 2024, *Scaling Synthetic Data Creation with
  1,000,000,000 Personas*, arXiv 2406.20094.
- Survey of generation, curation and evaluation: Long et al. 2024, *On LLMs-Driven Synthetic Data Generation,
  Curation, and Evaluation: A Survey*, Findings of ACL 2024, pp. 11065-11082.
- The questionnaire's interest options follow Holland's six types (Holland 1997, *Making Vocational Choices*, 3rd
  ed., PAR) and Prediger's work tasks (Prediger 1982, *Journal of Vocational Behavior* 21, 259-287), as used by the
  O*NET Interest Profiler (Lewis and Rivkin 1999; manual: Rounds, Hoff and Lewis 2021).
- Several LLM families; a held-out family for testing. Training: Qwen 2.5 (Alibaba), Aya Expanse (Cohere),
  Gemma 2 (Google). Testing: SeaLLM-7B-v2 (DAMO Academy, built on Mistral 7B). SeaLLM's outputs are used only as test
  data, never to train or improve a language model (SeaLLMs License Agreement); notice: "SeaLLMs is licensed under
  the SeaLLMs LICENSE AGREEMENT, Copyright (c) Damo Academy."

**Before running (Kaggle)**: the same as the chat notebook. Accelerator *GPU T4 x2*, Internet *on*, the `HF_TOKEN`
secret with the Aya Expanse and Gemma 2 licences accepted. Run once with `TRIAL = True` (3 groups x 2 students, a few
minutes) and send the printed output or `student_generated_<family>_trial.csv` for a check before the long run. Choose the families in `RUN_FAMILIES` (one or two per
session keeps you inside Kaggle's time limit; each family is saved separately, and partial files are written every
few batches so a stopped session keeps its work).

**Output**: `/kaggle/working/student_generated_<family>.csv` (columns `student_id, target_group, family, model,
attributes, raw, answers`; `answers` is the parsed JSON, empty when the model's output was not valid JSON) and
`student_review_sample_<family>.csv` (3 students per group, for people to check). Download them into the repo's
`pipelines/data/students/generated/` (review samples into `pipelines/data/students/review/`).
"""

CONFIG = r"""# ---- settings ----------------------------------------------------------------------------------------------
TRIAL = False                  # True: 3 groups x 2 students, to check the output and which engine ran
RUN_FAMILIES = ["qwen"]        # then aya, gemma; mistral (SeaLLM) is the held-out test family
STUDENTS_PER_GROUP = {"qwen": 40, "aya": 40, "gemma": 10, "mistral": 15}   # 74 groups: about 3,000 per family
MAX_HOURS = 11.0               # stop cleanly and save before Kaggle's 12-hour limit
REQUIRE_PREVIOUS = False       # True: stop at once if no earlier file of the family is attached (a top-up run)
# Resume: attach an earlier student_generated_<family>.csv (as a Kaggle dataset); its students are kept and skipped.
MAX_NEW_TOKENS = 700           # answers are option codes (since 2026-10-09), shorter than the copied labels before
TEMPERATURE, TOP_P = 0.9, 0.95
SEED = 2027

MODELS = {
    # family: (model id, how the transformers engine loads it). fp16 on T4 (no bf16); Gemma 2 overflows in fp16.
    "qwen":    ("Qwen/Qwen2.5-7B-Instruct", "fp16"),
    "aya":     ("CohereLabs/aya-expanse-8b", "fp16"),
    "gemma":   ("google/gemma-2-9b-it", "4bit_fp32"),
    "mistral": ("SeaLLMs/SeaLLM-7B-v2", "fp16"),        # held-out test family (Mistral 7B base)
}

# Engines, tried in order. "vllm": continuous batching with paged attention (Kwon et al. 2023, SOSP), the model split
# over both T4s, up to 128 students at once, the shared questionnaire computed once (prefix caching): about 10x the
# first runs. It runs in its own process, so a model it cannot load falls through to "transformers" (the first runs'
# engine: slow, known to work for every family).
ENGINES = {"qwen": ["vllm", "transformers"], "aya": ["vllm", "transformers"], "gemma": ["vllm", "transformers"],
           "mistral": ["vllm", "transformers"]}
# max_num_batched_tokens: vLLM 0.28 doubled its default to 16384, more memory than a T4 has to spare
VLLM = {"tensor_parallel_size": 2, "dtype": "half", "max_model_len": 4096, "gpu_memory_utilization": 0.90,
        "max_num_seqs": 128, "max_num_batched_tokens": 8192, "enable_prefix_caching": True}
# Gemma 2 cannot run in fp16 (vLLM refuses it: overflow) and T4s have no bf16: 4-bit weights, fp32 compute. Since vLLM
# 0.28 bitsandbytes is a separate plugin (vllm-bnb-plugin, installed below; without it: "Unknown quantization method:
# bitsandbytes", gemma run of 2026-10-09). If vLLM cannot load it, the log says so and the transformers engine takes
# over.
VLLM_MODEL = {"gemma": {"dtype": "float32", "quantization": "bitsandbytes"}}
CHUNK = 256                    # vLLM: students per chunk; the results are saved after every chunk
BATCH_SIZE = 8                 # transformers engine: 16 runs out of memory on 2x T4 (runs of 2026-10-08)
SAVE_EVERY = 10                # transformers engine: batches between partial saves
"""

INSTALL = r"""!pip install -q -U vllm vllm-bnb-plugin bitsandbytes accelerate
# Kaggle's preinstalled torchaudio can be built for another CUDA than the torch vllm brings, and transformers then fails
# on import; nothing here uses torchaudio
!pip uninstall -q -y torchaudio
import subprocess, sys
check = subprocess.run([sys.executable, "-c", "import torch, vllm, transformers; print('vllm', vllm.__version__, "
                        "'| torch', torch.__version__, '| transformers', transformers.__version__)"],
                       capture_output=True, text=True)
print(check.stdout or check.stderr[-3000:])
VLLM_OK = check.returncode == 0
if not VLLM_OK:
    print("vllm does not import (above): the transformers engine will be used, much slower")
"""


# Attributes sampled per prompt (Yu et al. 2023) and short personas (Chan et al. 2024). Written for this notebook;
# none names a nhóm ngành, and none ties a kind of student to a gender.
ATTRIBUTES = {
    "clarity": ["rất rõ mình thích gì", "khá rõ mình thích gì", "còn phân vân, thích cả vài hướng khác nhau"],
    "subjects": ["các môn em học tốt nhất hợp với nhóm ngành này", "các môn em học tốt nhất hợp với nhóm ngành này",
                 "các môn em học tốt nhất lại không liên quan nhiều đến nhóm ngành này"],
    "skips": ["trả lời đủ mọi câu", "trả lời đủ mọi câu", "bỏ qua 1-2 câu em thấy khó", "bỏ qua 3-4 câu"],
    "picks": ["chọn ít, chỉ những gì thật sự đúng", "chọn vừa phải", "chọn khá nhiều"],
    "level": ["học lực trung bình", "học lực khá", "học lực khá", "học lực giỏi"],
    "free_text": ["để trống", "một câu ngắn", "hai ba câu", "một đoạn dài, kể cả hoàn cảnh"],
    "free_text_style": ["có dấu đầy đủ", "có dấu đầy đủ", "không dấu", "viết tắt kiểu teencode (k, ko, dc, e, j)"],
    "mentions_job": ["không nhắc tên nghề nào", "không nhắc tên nghề nào", "có nhắc một nghề em mơ ước"],
}
PERSONAS = [
    "học sinh một trường THPT ở thị trấn nhỏ", "học sinh trường chuyên ở thành phố lớn",
    "học sinh hay tham gia câu lạc bộ ở trường", "học sinh ít nói, thích ở nhà", "học sinh hay phụ giúp việc của gia đình",
    "học sinh thích đọc sách và tìm hiểu trên mạng", "học sinh từng đi làm thêm vào dịp hè",
    "học sinh có bố mẹ làm nông", "học sinh có bố mẹ làm công nhân", "học sinh có bố mẹ làm nhân viên văn phòng",
    "học sinh có bố mẹ buôn bán nhỏ", "học sinh học ở miền núi", "học sinh hay làm lớp trưởng hoặc cán bộ lớp",
    "học sinh mê một môn thể thao", "học sinh thích công nghệ mới",
]

GENERATE = r"""import glob, json, random, re, subprocess, sys, time
random.seed(SEED)

# How many options a student ticks per multi-choice question, by the "picks" attribute (a range; capped by the
# question's max). Disliked subjects / topics (q2, q7) and "không muốn" (q12) are ticked less.
PICK_RANGE = {"chọn ít, chỉ những gì thật sự đúng": (1, 2), "chọn vừa phải": (2, 3), "chọn khá nhiều": (3, 5)}
FEWER = {"q2", "q7", "q12"}
SKIP_RANGE = {"trả lời đủ mọi câu": (0, 0), "bỏ qua 1-2 câu em thấy khó": (1, 2), "bỏ qua 3-4 câu": (3, 4)}

def plan_answers(attrs, rng):
    # The attributes as concrete instructions per question (the trial run showed that "chọn ít" alone is ignored).
    skip = set(rng.sample([q["id"] for q in QUESTIONS if q["id"] != "q1"], rng.randint(*SKIP_RANGE[attrs["skips"]])))
    counts = {}
    for q in QUESTIONS:
        if q["id"] in skip:
            counts[q["id"]] = None
        elif q["kind"] == "single":
            counts[q["id"]] = 1
        else:
            lo, hi = PICK_RANGE[attrs["picks"]]
            if q["id"] in FEWER:
                lo, hi = max(0, lo - 1), max(1, hi - 2)
            counts[q["id"]] = min(rng.randint(lo, hi), q.get("max") or 99, len(q["options"]))
    return counts

# A question whose options are those of an earlier one (q2 = q1, q7 = q6) points to it instead of repeating them.
SAME_AS = {}
for i, q in enumerate(QUESTIONS):
    for p in QUESTIONS[:i]:
        if q["codes"] == p["codes"] and p["id"] not in SAME_AS:
            SAME_AS[q["id"]] = p["id"]
            break

def questionnaire_text():
    lines = []
    for q in QUESTIONS:
        kind = "chọn một mã" if q["kind"] == "single" else "chọn nhiều mã"
        rule = f", không trùng với {q['not_in']}" if q.get("not_in") else ""
        opts = (f"dùng các mã của {SAME_AS[q['id']]}" if q["id"] in SAME_AS else
                " | ".join(f"{c}={label}" for c, label in zip(q["codes"], q["options"])))
        lines.append(f"{q['id']}. {q['text']} ({kind}{rule}): {opts}")
    return "\n".join(lines)

# The part every prompt shares, first, so vLLM computes it once (prefix caching); the student comes after it. The
# writer answers with option codes, not labels: shorter outputs and fewer copying mistakes
# (2026-10-09). The example shows the shape only (a trial writer once copied an example score).
PREFIX = (
    "Bạn giúp tạo dữ liệu huấn luyện cho một ứng dụng tư vấn chọn ngành đại học ở Việt Nam. Ở cuối có mô tả MỘT học "
    "sinh lớp 12: hãy tưởng tượng học sinh đó và điền bảng câu hỏi như em ấy tự điền.\n\n"
    "BẢNG CÂU HỎI. Mỗi lựa chọn viết dạng MÃ=nội dung. Trả lời bằng MÃ, chép đúng mã, chỉ dùng mã của chính câu đó.\n"
    f"{questionnaire_text()}\n"
    "diem: điểm thi dự kiến, một đối tượng {MÃ môn: điểm}, mã môn lấy từ q1; mỗi điểm từ 0 đến 10, bước 0,25, hợp với "
    "học lực và các môn em học tốt; điểm như học sinh thật, mỗi môn một điểm khác nhau.\n"
    "ke_them: phần 'Kể thêm về em', học sinh tự viết bằng tiếng Việt, xưng 'em' hoặc 'mình'. Không nhắc tên nhóm "
    "ngành hay tên ngành. Không chép lại các dòng mô tả học sinh (trường, học lực, mức độ phân vân): viết điều em "
    "thích, điều em không muốn.\n\n"
    "QUY TẮC\n"
    "- Chọn ĐÚNG số mã ghi cho từng câu ở phần mô tả học sinh. Câu BỎ QUA: null. Câu 'không chọn gì': [].\n"
    "- Câu chọn nhiều: một mảng JSON các mã. Câu chọn một: một chuỗi mã.\n"
    "- Học sinh thật không hoàn hảo: không chọn mọi thứ liên quan đến ngành, có thể thích cả vài điều không liên quan.\n"
    '- Chỉ trả về MỘT đối tượng JSON với các khóa "q1" đến "q12", "diem" và "ke_them". Không giải thích.\n'
    'Dạng (không phải nội dung): {"q1": ["<mã>", "<mã>"], "q2": null, ..., "q9": "<mã>", ..., '
    '"diem": {"<mã môn>": <điểm>}, "ke_them": "<chuỗi>"}\n\n'
)

def plan_text(counts):
    parts = []
    for q in QUESTIONS:
        k = counts[q["id"]]
        how = ("BỎ QUA (null)" if k is None else "chọn 1 mã" if q["kind"] == "single" else
               "không chọn gì ([])" if k == 0 else f"chọn đúng {k} mã")
        parts.append(f"{q['id']}: {how}")
    return "; ".join(parts)

def build_prompt(group, rng):
    attrs = {k: rng.choice(v) for k, v in ATTRIBUTES.items()}
    attrs["persona"] = rng.choice(PERSONAS)
    counts = plan_answers(attrs, rng)
    n_scores = rng.randint(4, 6)
    attrs["counts"], attrs["n_scores"], attrs["format"] = counts, n_scores, "codes"
    nganh = ", ".join(group["nganh"])
    # "để trống" spelt out as the JSON value: asked in words, no writer of the first runs left the text empty
    text = ('"" (chuỗi rỗng: em để trống phần này)' if attrs["free_text"] == "để trống" else
            f"{attrs['free_text']}; {attrs['free_text_style']}; {attrs['mentions_job']}")
    prompt = PREFIX + (
        "HỌC SINH CẦN TƯỞNG TƯỢNG\n"
        f"Nhóm ngành hợp với em: {group['name']} (gồm các ngành: {nganh}).\n"
        f"Em là {attrs['persona']}; {attrs['level']}; {attrs['clarity']}; {attrs['subjects']}.\n"
        f"Số mã chọn ở mỗi câu: {plan_text(counts)}.\n"
        f"diem: ĐÚNG {n_scores} môn khác nhau.\n"
        f"ke_them: {text}."
    )
    return prompt, attrs

def parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None

def known(q, x):
    # An answer naming one of the question's options: its code (any case) or, in the first runs' files, its label.
    return isinstance(x, str) and (x.strip().lower() in {c.lower() for c in q["codes"]} or x in q["options"])

def follows(answers, attrs):
    # Problems with one student against its plan: {"count": [...], "foreign": [...], "skip": [...], "scores": n}
    out = {"count": [], "foreign": [], "skip": [], "scores": 0}
    for q in QUESTIONS:
        k, a = attrs["counts"][q["id"]], answers.get(q["id"])
        picked = [] if a is None else ([a] if isinstance(a, str) else list(a))
        if k is None:
            if picked:
                out["skip"].append(q["id"])
            continue
        if len(picked) != k:
            out["count"].append(q["id"])
        out["foreign"] += [f"{q['id']}:{x}" for x in picked if not known(q, x)]
    diem = answers.get("diem")
    out["scores"] = len(diem) if isinstance(diem, dict) else 0
    return out

def summary(rows):
    checked = [(json.loads(r["answers"]), json.loads(r["attributes"])) for r in rows if r["answers"]]
    if not checked:
        return "nothing parsed"
    f = [follows(a, t) for a, t in checked]
    n = len(f)
    return (f"{n} parsed of {len(rows)}; wrong number of picks: {sum(len(x['count']) for x in f)} questions in "
            f"{sum(bool(x['count']) for x in f)} students; options from another question or misspelt: "
            f"{sum(len(x['foreign']) for x in f)}; skipped questions answered: {sum(len(x['skip']) for x in f)}; "
            f"scores as asked: {sum(x['scores'] == t['n_scores'] for x, (_, t) in zip(f, checked))}/{n}")

def row(sid, group, family, attrs, text, engine):
    answers = parse(text)
    return {"student_id": sid, "target_group": group, "family": family, "model": MODELS[family][0],
            "attributes": json.dumps({**attrs, "engine": engine}, ensure_ascii=False), "raw": text,
            "answers": json.dumps(answers, ensure_ascii=False) if answers else ""}

def save(rows, family, final=False):
    tag = f"{family}_trial" if TRIAL else family
    df = pd.DataFrame(rows)
    df.to_csv(f"/kaggle/working/student_generated_{tag}.csv", index=False)
    if final and len(df):
        (df.sample(frac=1, random_state=SEED).groupby("target_group").head(3).sort_values("target_group")
           .to_csv(f"/kaggle/working/student_review_sample_{tag}.csv", index=False))
    return df

def previous(family):
    # Students of an earlier run of this family: any CSV attached as an input dataset (whatever Kaggle named it) with
    # this notebook's columns and only this family's students.
    rows = []
    files = sorted(glob.glob("/kaggle/input/**/*.csv", recursive=True))
    for path in files:
        if os.path.basename(path).startswith("student_review_sample"):   # a sample of a run, not more students
            continue
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
        except Exception:
            continue
        if {"student_id", "family", "answers", "raw"} <= set(df.columns) and len(df) and set(df["family"]) == {family}:
            rows += df.to_dict("records")
            print("resuming from", path, len(df), "students")
    if not rows and REQUIRE_PREVIOUS:
        print("CSV files under /kaggle/input:", files or "none")
        raise SystemExit(f"No earlier {family} file is attached: add the dataset with student_generated_{family}.csv "
                         "(Add Input), then run again. Stopped before loading the model, so no GPU time is used.")
    return list({r["student_id"]: r for r in rows}.values())

# ---- vLLM engine: its own process (a failed load cannot take the notebook down), results appended per chunk ----
WORKER = '''import json, sys, time
from vllm import LLM, SamplingParams

def main():
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    t0 = time.time()
    llm = LLM(model=job["model"], seed=job["seed"], **job["engine"])
    print(f"vLLM: {job['model']} loaded in {time.time() - t0:.0f} s", flush=True)
    params = SamplingParams(temperature=job["temperature"], top_p=job["top_p"], max_tokens=job["max_tokens"],
                            seed=job["seed"])
    tok = llm.get_tokenizer()
    items = job["items"]
    with open(job["out"], "a", encoding="utf-8") as f:
        for b in range(0, len(items), job["chunk"]):
            if time.time() > job["deadline"]:
                print("vLLM: stopped at the time limit", flush=True)
                break
            chunk = items[b:b + job["chunk"]]
            if tok.chat_template:
                outs = llm.chat([[{"role": "user", "content": p}] for _, p in chunk], params, use_tqdm=False)
            else:   # SeaLLM-7B-v2 ships no template: its documented format (vLLM adds the BOS itself)
                prompts = [f"<|im_start|>user\\n{p}</s><|im_start|>assistant\\n" for _, p in chunk]
                outs = llm.generate(prompts, params, use_tqdm=False)
            for (sid, _), o in zip(chunk, outs):
                f.write(json.dumps({"student_id": sid, "text": o.outputs[0].text}, ensure_ascii=False) + "\\n")
            f.flush()
            print(f"vLLM: {b + len(chunk)}/{len(items)} students, {time.time() - t0:.0f} s", flush=True)

# vLLM may start its engine processes with "spawn", which imports this file again: run only as the script
if __name__ == "__main__":
    main()
'''

def run_vllm(family, todo, deadline):
    # {student_id: text} written by vLLM, and the worker's exit code (0: finished or stopped at the time limit).
    work = "/kaggle/working"
    out, job_path, worker = f"{work}/vllm_{family}.jsonl", f"{work}/vllm_job_{family}.json", f"{work}/vllm_worker.py"
    if os.path.exists(out):
        os.remove(out)
    with open(worker, "w", encoding="utf-8") as f:
        f.write(WORKER)
    job = {"model": MODELS[family][0], "engine": {**VLLM, **VLLM_MODEL.get(family, {})}, "seed": SEED,
           "temperature": TEMPERATURE, "top_p": TOP_P, "max_tokens": MAX_NEW_TOKENS, "chunk": CHUNK,
           "deadline": deadline, "out": out, "items": [[j[0], j[2]] for j in todo]}
    with open(job_path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False)
    proc = subprocess.Popen([sys.executable, worker, job_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=dict(os.environ))
    tail = []
    for line in proc.stdout:              # the worker's log, shown as it runs
        tail = (tail + [line])[-40:]
        if line.startswith("vLLM:") or "Error" in line or "error" in line[:80]:
            print(line, end="")
    code = proc.wait()
    if code:
        print("".join(tail))
    texts = {}
    if os.path.exists(out):
        for line in open(out, encoding="utf-8"):
            r = json.loads(line)
            texts[r["student_id"]] = r["text"]
    return texts, code

# ---- transformers engine (the first runs'): slow, known to work for every family ----
""" + "%MODEL_HELPERS%" + r"""
def run_transformers(family, todo, rows, deadline):
    model_id, how = MODELS[family]
    tok, model = load(model_id, how)
    start = time.time()
    for i, b in enumerate(range(0, len(todo), BATCH_SIZE)):
        if time.time() > deadline:
            print(f"{family}: stopped after {MAX_HOURS} h to stay inside Kaggle's limit; resume in a new session")
            break
        batch = todo[b:b + BATCH_SIZE]
        enc = tok([chat_text(tok, j[2]) for j in batch], return_tensors="pt", padding=True,
                  add_special_tokens=False).to(model.device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=MAX_NEW_TOKENS, do_sample=True, temperature=TEMPERATURE,
                                 top_p=TOP_P, pad_token_id=tok.pad_token_id)
        texts = tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        rows += [row(sid, group, family, attrs, text, "transformers")
                 for (sid, group, _, attrs), text in zip(batch, texts)]
        if i % SAVE_EVERY == 0:
            save(rows, family)
            ok = sum(bool(r["answers"]) for r in rows)
            print(f"{family}: {b + len(batch)}/{len(todo)} students, {ok} parsed, {time.time() - start:.0f}s")
    del model
    gc.collect()
    torch.cuda.empty_cache()

def run_family(family):
    rng = random.Random(f"{SEED}-{family}")
    jobs = []
    for group in (GROUPS[:3] if TRIAL else GROUPS):
        for k in range(2 if TRIAL else STUDENTS_PER_GROUP[family]):
            prompt, attrs = build_prompt(group, rng)
            jobs.append((f"{family}-{group['code']}-{k}", group["code"], prompt, attrs))
    rng.shuffle(jobs)                      # groups mixed in every chunk: a stopped run still covers all groups
    rows = previous(family)
    if TRIAL:                              # a trial checks the attached file but writes fresh students to *_trial.csv
        print(f"{family}: trial; the {len(rows)} students of the attached file are left as they are")
        rows = []
    done = {r["student_id"] for r in rows}
    jobs = [j for j in jobs if j[0] not in done]
    print(f"{family}: {len(rows)} students from an earlier run kept, {len(jobs)} to generate")
    deadline = time.time() + MAX_HOURS * 3600
    for engine in ENGINES[family]:
        todo = [j for j in jobs if j[0] not in {r["student_id"] for r in rows}]
        if not todo or time.time() > deadline:
            break
        if engine == "vllm":
            if not VLLM_OK:
                continue
            start = time.time()
            texts, code = run_vllm(family, todo, deadline)
            rows += [row(sid, group, family, attrs, texts[sid], "vllm") for sid, group, _, attrs in todo if sid in texts]
            save(rows, family)
            if len(texts):
                print(f"{family}: vLLM wrote {len(texts)} students in {time.time() - start:.0f} s "
                      f"({(time.time() - start) / len(texts):.2f} s per student, model loading included)")
            if code == 0:
                break
            print(f"{family}: vLLM stopped with exit code {code} (log above); the next engine takes over")
        else:
            run_transformers(family, todo, rows, deadline)
            break
    df = save(rows, family, final=True)
    print(family, "done:", len(df), "students,", int((df["answers"] != "").sum()), "parsed")
    print(summary(rows))
    if TRIAL:
        for r in rows:
            print("\n", r["target_group"], r["attributes"], "\n", r["raw"][:1500])
    return df

results = {f: run_family(f) for f in RUN_FAMILIES}
"""

OUTRO = r"""## After the run

1. Download `student_generated_<family>.csv` into `pipelines/data/students/generated/` and `student_review_sample_<family>.csv`
   into `pipelines/data/students/review/` of the repository.
2. People read the review samples: does the student
   believably suit the target group? Is another group a better fit?
3. Then clean the answers (labels mapped back to option codes), audits writer habits (how often each
   group's students tick each option against everyone), and trains the model.
"""


def groups(d: AppData, exclude: tuple[str, ...]) -> list[dict]:
    cat = d.catalog
    out = []
    for code, m in sorted(cat.majors.items()):
        if m.level != "nhom_nganh" or code in exclude:
            continue
        nganh = [cat.majors[c].label for c in m.children][:MAX_NGANH_SHOWN]
        out.append({"code": code, "name": m.label, "nganh": nganh})
    return out


# Top-up runs: a family's first session was cut off; the notebook resumes from the attached file and adds the missing
# students, stopping cleanly after MAX_HOURS. Gemma (2026-10-08): 728 students (5-18 per group), up to 20 per group,
# run overnight. Aya (2026-10-09): 2,008 of 2,960 after 10.9 h (about 19.6 s per student), on an account
# with 5.5 GPU hours left: 4.6 h of generation leaves time for installing and loading the model and a margin (a
# committed run killed by the quota loses its output).
TOPUPS = {
    "gemma": {"model": "Gemma 2 9B", "hf_page": "google/gemma-2-9b-it", "had": 728, "per_group": 20, "hours": 11.0},
    "aya": {"model": "Aya Expanse 8B", "hf_page": "CohereLabs/aya-expanse-8b", "had": 2008, "per_group": 40,
            "hours": 4.6},
}


def topup_out(family: str) -> Path:
    return OUT.parent / f"student_generation_{family}_topup.ipynb"


def topup_settings(family: str) -> dict[str, str]:
    t = TOPUPS[family]
    per_group = {"qwen": 40, "aya": 40, "gemma": 10, "mistral": 15}
    per_group[family] = t["per_group"]
    return {
        'RUN_FAMILIES = ["qwen"]        # then aya, gemma; mistral (SeaLLM) is the held-out test family':
            f'RUN_FAMILIES = ["{family}"]  # top-up run: {t["model"]} only',
        'STUDENTS_PER_GROUP = {"qwen": 40, "aya": 40, "gemma": 10, "mistral": 15}':
            "STUDENTS_PER_GROUP = {" + ", ".join(f'"{f}": {n}' for f, n in per_group.items()) + "}",
        "MAX_HOURS = 11.0               # stop cleanly and save before Kaggle's 12-hour limit":
            f"MAX_HOURS = {t['hours']}               # top-up run: stop cleanly and save inside the GPU time left",
        'REQUIRE_PREVIOUS = False       # True: stop at once if no earlier file of the family is attached (a top-up run)':
            f'REQUIRE_PREVIOUS = True        # top-up run: stop at once if the earlier {family} file is not attached',
    }


def topup_howto(family: str) -> str:
    t = TOPUPS[family]
    return f"""# Chạy bổ sung dữ liệu {t["model"]}

Notebook này tạo thêm học sinh mẫu bằng mô hình {t["model"]}, **nối tiếp** tệp đã có (`student_generated_{family}.csv`,
{t["had"]:,} học sinh), tới {t["per_group"]} học sinh mỗi nhóm. Máy tự dừng sau khoảng {t["hours"]:g} giờ sinh dữ liệu
(cộng khoảng 15-20 phút cài đặt và tải mô hình) và lưu kết quả, nên có thể bấm chạy rồi đi ngủ.

**Chuẩn bị (khoảng 10 phút):**

1. **Tài khoản Hugging Face:** đăng nhập https://huggingface.co, mở trang `{t["hf_page"]}` và bấm đồng ý điều khoản
   (nếu chưa). Tạo token đọc (Settings → Access Tokens → New token, quyền *Read*).
2. **Kaggle → Add-ons → Secrets:** thêm secret tên `HF_TOKEN`, giá trị là token ở bước 1, và bật cho notebook này.
3. **Tải tệp cũ lên làm dataset:** Kaggle → Datasets → New dataset → tải lên `student_generated_{family}.csv` (**giữ
   nguyên tên tệp**). Trong notebook: Add Input → chọn dataset vừa tạo.
4. **Cài đặt notebook (cột bên phải):** Accelerator = **GPU T4 x2**; Internet = **On**.

**Chạy:** bấm **Save Version** → **Save & Run All (Commit)** → Save. Không cần mở trình duyệt khi máy chạy.

**Sau khi chạy xong:** mở notebook → tab *Output* của phiên bản vừa chạy → tải `student_generated_{family}.csv` (và
`student_review_sample_{family}.csv` nếu có). Tệp mới đã gồm cả {t["had"]:,} học sinh cũ.

**Nếu log báo `No earlier {family} file is attached`:** notebook đã tự dừng (chưa tốn GPU). Gắn lại dataset (Add Input →
Your Work → Datasets) rồi chạy lại; tên tệp trong dataset có bị Kaggle đổi cũng không sao.

**Kiểm tra nhanh trong log:** dòng `{family}: N students from an earlier run kept, ... to generate` ở đầu, với N là số
học sinh trong tệp đã gắn (nếu ghi `0 students from an earlier run` là chưa gắn đúng dataset ở bước 3: dừng lại và gắn
lại). Sau đó:

- **Máy chạy nhanh (vLLM):** có dòng `vLLM: ... loaded in ... s`, rồi định kỳ `vLLM: .../... students, ... s`. Cuối cùng
  có dòng `vLLM wrote ... students in ... s (... s per student ...)`.
- **vLLM không chạy được mô hình này:** log ghi `vLLM stopped with exit code ...` kèm lỗi, rồi notebook tự chuyển sang
  cách chạy cũ (chậm hơn nhiều), với dòng `{family}: .../... students, ... parsed`. Không cần làm gì, nhưng hãy gửi
  lại đoạn log lỗi đó cho nhóm.

**Nên chạy thử trước (khoảng 15-30 phút):** đặt `TRIAL = True` trong ô cài đặt, chạy, xem log có dòng `vLLM wrote`
không, rồi đặt lại `TRIAL = False` và chạy thật.
"""


def build(topup: str | None = None) -> dict:
    qn = load_questionnaire()
    d = AppData.load()
    questions = [{"id": q.id, "text": q.text, "kind": q.kind, "max": q.max, "not_in": q.not_in,
                  "codes": [o.code for o in q.options], "options": [o.label for o in q.options]} for q in qn.questions]
    subjects = [o.label for o in qn.get("q1").options]
    values = {"QUESTIONS": questions, "GROUPS": groups(d, qn.exclude_groups), "SUBJECTS": subjects,
              "ATTRIBUTES": ATTRIBUTES, "PERSONAS": PERSONAS}
    data_cell = "\n\n".join(f"{k} = {pformat(v, width=118, sort_dicts=False)}" for k, v in values.items()) + "\n"
    config = CONFIG
    if topup:
        for old, new in topup_settings(topup).items():
            assert config.count(old) == 1, old
            config = config.replace(old, new)
    cells = [_cell("markdown", INTRO), _cell("code", config), _cell("code", INSTALL), _cell("code", LIBS),
             _cell("markdown", "## Questionnaire, target groups, attributes and personas (from UniAdvisor's data)"),
             _cell("code", data_cell), _cell("markdown", "## Generation"),
             _cell("code", GENERATE.replace("%MODEL_HELPERS%", MODEL_HELPERS)), _cell("markdown", OUTRO)]
    if topup:
        cells.insert(0, _cell("markdown", topup_howto(topup)))
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                                        "name": "python3"},
                                         "language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for path, topup in ((OUT, None), *((topup_out(f), f) for f in TOPUPS)):
        path.write_text(json.dumps(build(topup), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
