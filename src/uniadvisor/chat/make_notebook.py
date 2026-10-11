"""Write notebooks/chat_message_generation.ipynb: the Kaggle notebook that has open LLMs write Vietnamese chat messages
for training the message classifier (spec 5). It runs on Kaggle (2x T4).

The notebook embeds the names it may use (schools, ngành, subjects) from the database, so it needs no other input.
No student data is involved.

Run: python -m uniadvisor.chat.make_notebook
"""

from __future__ import annotations

import json

from uniadvisor.app.service import AppData
from uniadvisor.paths import ROOT

OUT = ROOT / "notebooks" / "chat_message_generation.ipynb"

INTRO = r"""# UniAdvisor: chat messages for training the message classifier

Writes Vietnamese messages a grade-12 student (or a parent) might type into UniAdvisor's chat, labelled with one of 19
request types (`src/uniadvisor/chat/types.py`). The labels are known by construction: each prompt asks for messages of
one given type.

**Method (cited, verified 2026-10-06)**
- Prompting off-the-shelf LLMs with a description and seed examples of one intent to generate labelled training data:
  Sahu et al. 2022, *Data Augmentation for Intent Classification with Off-the-shelf Large Language Models*,
  4th Workshop on NLP for Conversational AI (ACL 2022), pp. 47-57.
- Attributed prompts (each prompt samples style, length, accents, typos, persona) for diversity and less bias:
  Yu et al. 2023, *Large Language Model as Attributed Training Data Generator: A Tale of Diversity and Bias*,
  NeurIPS 2023 Datasets and Benchmarks.
- Survey of generation, curation and evaluation: Long et al. 2024, *On LLMs-Driven Synthetic Data Generation,
  Curation, and Evaluation: A Survey*, Findings of ACL 2024, pp. 11065-11082.
- Several LLM families, and a held-out family for testing (spec 5). Families here: Qwen 2.5 (Alibaba), Aya Expanse
  (Cohere), Gemma 2 (Google) for training; SeaLLM-7B-v2 (DAMO Academy, built on Mistral 7B, supports Vietnamese)
  for testing. Vistral-7B-Chat, the first choice, needs a manual approval by its authors that did not come.
  SeaLLM's outputs are used only as test messages, never to train or improve a language model (SeaLLMs License
  Agreement); notice: "SeaLLMs is licensed under the SeaLLMs LICENSE AGREEMENT, Copyright (c) Damo Academy."

**Before running (Kaggle)**
1. Settings: Accelerator *GPU T4 x2*, Internet *on*.
2. Gated models: with your Hugging Face account, accept the licences of `CohereLabs/aya-expanse-8b`,
   `google/gemma-2-9b-it` (SeaLLM and Qwen are not gated), then add a Kaggle secret named `HF_TOKEN` (Add-ons ->
   Secrets). Qwen is not gated. Aya Expanse is CC-BY-NC (non-commercial use only).
3. Choose the families to run in `RUN_FAMILIES` (one or two per session keeps you inside Kaggle's time limit).

**Output**: `/kaggle/working/chat_generated_<family>.csv` (round 2: `<family>_round2`) (columns `text, type, family, model, attributes, prompt_id`)
and `chat_review_sample_<family>.csv` (20 messages per type for people to check, spec 5). Download them into the repo's
`data/chat/generated/` (review samples into `data/chat/review/`), then run `python -m uniadvisor.chat.train`.
"""

CONFIG = r"""# ---- settings ----------------------------------------------------------------------------------------------
# Round 2 (2026-10-08): only the three types added after round 1, for every family (round 1 files are kept).
RUN_FAMILIES = ["qwen", "aya", "gemma", "mistral"]
RUN_TYPES = ["favorite_school", "own_score", "cutoff_shift"]   # None: every type
ROUND = 2                      # in the output file names, so round 1's files are not overwritten
PROMPTS_PER_TYPE = 40          # prompts per request type and family
MESSAGES_PER_PROMPT = 5        # messages asked for in one prompt
BATCH_SIZE = 8
MAX_NEW_TOKENS = 400
TEMPERATURE, TOP_P = 0.9, 0.95
SEED = 2027

MODELS = {
    # family: (model id, how to load). fp16 on T4 (no bf16); Gemma 2 overflows in fp16, so it runs 4-bit with fp32 compute.
    "qwen":    ("Qwen/Qwen2.5-7B-Instruct", "fp16"),
    "aya":     ("CohereLabs/aya-expanse-8b", "fp16"),
    "gemma":   ("google/gemma-2-9b-it", "4bit_fp32"),
    "mistral": ("SeaLLMs/SeaLLM-7B-v2", "fp16"),        # held-out test family (Mistral 7B base)
}
"""

INSTALL = r"""!pip install -q -U transformers accelerate bitsandbytes
"""

LIBS = r"""import gc, json, os, random, re, time
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

try:
    from kaggle_secrets import UserSecretsClient
    os.environ["HF_TOKEN"] = UserSecretsClient().get_secret("HF_TOKEN")
except Exception as e:   # not on Kaggle, or no secret: only ungated models will load
    print("No HF_TOKEN secret:", e)
print(torch.cuda.device_count(), "GPU(s)")
"""

TYPES = {
    "change_score": ("đổi điểm một hoặc vài môn thi của em", "subjects_scores"),
    "change_priority": ("đổi khu vực ưu tiên (KV1, KV2-NT, KV2, KV3) hoặc đối tượng ưu tiên (ưu tiên 1 / nhóm đối tượng "
                        "01-03, ưu tiên 2 / nhóm 04-06, hoặc không ưu tiên)", "priority"),
    "change_budget": ("đổi ngân sách học phí mỗi năm (triệu đồng), hoặc bỏ giới hạn ngân sách", "budget"),
    "change_near_home": ("bật hoặc tắt mong muốn học gần nhà", "near_home"),
    "extra_points": ("nhập điểm cộng mà một trường cụ thể cho em (em đã tự tính theo quy định của trường)",
                     "school_points"),
    "favorite_school": ("chọn một trường là trường em thích nhất / muốn vào nhất (để trường đó được ưu tiên trong danh "
                        "sách), hoặc bỏ trường yêu thích đã chọn", "school_or_none"),
    "own_score": ("nhập điểm xét tuyển của em ở một trường, em đã tự tính theo cách tính riêng của trường đó (ví dụ "
                  "trường xét kết hợp điểm thi với học bạ hoặc điểm đánh giá năng lực, thang 30 hoặc thang 100)",
                  "school_own_score"),
    "cutoff_shift": ("nói rằng điểm chuẩn của một trường, với em, thực ra cao hơn hoặc thấp hơn con số công bố (ví dụ "
                     "trường đó có nhiều điểm cộng nên điểm chuẩn bị đẩy lên), để ứng dụng điều chỉnh cho riêng em",
                     "school_shift"),
    "remove": ("bỏ một trường (mọi chương trình của trường) hoặc một nguyện vọng theo số thứ tự NV khỏi danh sách",
               "school_or_nv"),
    "restore": ("đưa lại vào danh sách một trường hoặc nguyện vọng em đã bỏ trước đó", "school_or_removed"),
    "rerank": ("đổi thứ tự hai lựa chọn ngành của em (lựa chọn 2 lên trước lựa chọn 1)", "none"),
    "replace_nganh": ("thay một lựa chọn ngành bằng ngành khác, hoặc thêm / bỏ / đổi một ngành gần của lựa chọn",
                      "two_nganh"),
    "undo": ("hoàn tác thay đổi vừa làm", "none"),
    "ask_why_nv": ("hỏi vì sao một chương trình lại nằm ở nguyện vọng số N trong danh sách", "nv"),
    "ask_why_not": ("hỏi vì sao một trường không có trong danh sách nguyện vọng", "school"),
    "ask_compare": ("hỏi hai ngành khác nhau thế nào / nên chọn ngành nào", "two_nganh"),
    "ask_what_is": ("hỏi về một ngành: học gì, có khó không, cần giỏi môn nào, ra trường làm gì, thu nhập", "nganh"),
    "ask_level": ("hỏi một mức trong danh sách (an toàn, vừa sức, thử sức, mơ ước) nghĩa là gì", "level"),
    "other": ("nói chuyện ngoài lề hoặc nhờ việc ứng dụng không làm (chào hỏi, cảm ơn, hỏi dự đoán điểm chuẩn năm nay, "
              "xin số điện thoại, nhờ làm bài tập, tâm sự)", "none"),
}

# Seed examples per type (Sahu et al. 2022 prompt with a few examples). Written for this notebook; they are not in
# data/chat/checks.csv.
SEEDS = {
    "change_score": ["toán em 8,25 nha", "sửa điểm hóa thành 7", "anh van e dc 9.5"],
    "change_priority": ["em ở KV2-NT", "nhà em thuộc khu vực 1", "em không có đối tượng ưu tiên"],
    "change_budget": ["học phí tối đa 35 triệu/năm", "nhà em lo được tầm 20tr thôi", "không giới hạn học phí"],
    "change_near_home": ["em muốn học gần nhà", "đi xa cũng được ạ", "ko cần gần nhà"],
    "extra_points": ["trường Thương mại cộng cho em 1 điểm", "UEH cộng 0.75", "em được Bách khoa cộng 2 điểm IELTS"],
    "favorite_school": ["trường em thích nhất là Ngoại thương", "em muốn vào Bách khoa nhất", "bỏ trường yêu thích đi"],
    "own_score": ["điểm xét tuyển của em ở Bách khoa TP.HCM là 82", "em tự tính điểm ở UIT được 27,5",
                  "theo cách tính của trường Kinh tế Quốc dân thì e được 28"],
    "cutoff_shift": ["điểm chuẩn UIT nhiều điểm cộng lắm, thực ra thấp hơn 1 điểm", "điểm chuẩn NEU cao hơn thực tế 0,5",
                     "30 điểm của trường Ngoại thương không cao bằng 29 của Bách khoa đâu"],
    "remove": ["bỏ trường Văn Lang", "xoá NV4 giúp em", "em ko muốn học Ngoại thương"],
    "restore": ["cho Văn Lang vào lại", "lấy lại trường em vừa bỏ", "đưa NEU trở lại"],
    "rerank": ["đổi thứ tự 2 ngành", "cho lựa chọn 2 lên đầu", "hoán đổi hai lựa chọn"],
    "replace_nganh": ["thay Kế toán bằng Kiểm toán", "thêm ngành gần Marketing", "đổi lựa chọn 1 sang Luật"],
    "undo": ["hoàn tác", "quay lại như trước", "huỷ cái vừa đổi"],
    "ask_why_nv": ["sao NV2 lại là trường này", "vì sao nguyện vọng 9 ở đó", "giải thích NV1"],
    "ask_why_not": ["sao không có Bách khoa", "NEU đâu rồi", "vì sao thiếu trường Ngoại thương"],
    "ask_compare": ["Kế toán với Kiểm toán khác gì", "nên học Luật hay Luật kinh tế", "so sánh CNTT và KHMT"],
    "ask_what_is": ["ngành Logistics học gì", "Marketing ra làm gì", "Dược học có khó không"],
    "ask_level": ["thử sức là gì", "mức an toàn nghĩa là chắc đỗ à", "vừa sức là sao"],
    "other": ["chào bạn", "điểm chuẩn năm nay bao nhiêu", "giúp em làm bài toán này"],
}

ATTRIBUTES = {
    "writer": ["học sinh lớp 12", "học sinh lớp 12", "phụ huynh"],
    "register": ["thân mật, nói như nhắn tin với bạn", "lịch sự, có 'ạ', 'dạ'", "ngắn gọn, ra lệnh"],
    "accents": ["có dấu đầy đủ", "có dấu đầy đủ", "không dấu (telex chưa bật)", "lẫn lộn chỗ có dấu chỗ không"],
    "noise": ["không lỗi", "vài lỗi gõ phím", "dùng từ viết tắt kiểu teencode (k, ko, dc, e, j, ntn)"],
    "length": ["rất ngắn (dưới 6 từ)", "một câu ngắn", "một câu dài, có kể thêm hoàn cảnh"],
    "form": ["câu khẳng định hoặc mệnh lệnh", "câu hỏi", "kể / tường thuật"],
}

GENERATE = r"""random.seed(SEED)
LEVELS = ["an toàn", "vừa sức", "thử sức", "mơ ước"]

def score_text(rng):
    v = rng.choice([x / 4 for x in range(8, 41)])
    words = {5: "năm", 6: "sáu", 7: "bảy", 8: "tám", 9: "chín", 10: "mười"}
    if rng.random() < 0.15 and v == int(v) and int(v) in words:
        return words[int(v)]
    s = f"{v:g}"
    return s.replace(".", ",") if rng.random() < 0.5 else s

def slot_hint(kind, rng):
    # Values the messages should use, from UniAdvisor's real data (names) or random (numbers).
    if kind == "subjects_scores":
        subs = rng.sample(SLOTS["subjects"], rng.choice([1, 1, 2, 3]))
        return "môn và điểm: " + "; ".join(f"{s} {score_text(rng)}" for s in subs)
    if kind == "priority":
        return "giá trị: " + rng.choice(["KV1", "KV2-NT", "KV2", "KV3", "ưu tiên 1", "ưu tiên 2", "nhóm đối tượng 03",
                                         "nhóm đối tượng 06", "không thuộc đối tượng ưu tiên"])
    if kind == "budget":
        return "ngân sách: " + rng.choice([f"{rng.randrange(10, 101, 5)} triệu/năm", "không giới hạn",
                                           f"{rng.randrange(10, 101, 5)}tr"])
    if kind == "near_home":
        return "ý muốn: " + rng.choice(["muốn học gần nhà", "không cần học gần nhà"])
    if kind == "school_points":
        return f"trường: {rng.choice(SLOTS['schools'])}; điểm cộng: {rng.choice(['0,25', '0,5', '0.75', '1', '1,5', '2', '3'])}"
    if kind == "school_or_none":
        return rng.choice([f"trường: {rng.choice(SLOTS['schools'])}"] * 4 + ["bỏ trường yêu thích (không nói tên)"])
    if kind == "school_own_score":
        on_30 = f"{rng.randrange(20, 30)},{rng.choice(['0', '25', '5', '75'])}"
        score = rng.choice([f"{rng.randrange(55, 98)}/100", f"{rng.randrange(55, 98)} (thang 100)",
                            f"{on_30} (thang 30)", on_30])
        return f"trường: {rng.choice(SLOTS['schools'])}; điểm xét tuyển em tự tính: {score}"
    if kind == "school_shift":
        how = rng.choice(["thấp hơn", "cao hơn", "thấp hơn", "không nói số điểm, chỉ nói cao hơn / thấp hơn"])
        return (f"trường: {rng.choice(SLOTS['schools'])}; điểm chuẩn với em {how}"
                + ("" if how.startswith("không") else f" {rng.choice(['0,5', '1', '1,5', '2', '0.25', '3'])} điểm"))
    if kind == "school_or_nv":
        return rng.choice([f"trường: {rng.choice(SLOTS['schools'])}", f"nguyện vọng số {rng.randint(1, 15)}"])
    if kind == "school_or_removed":
        return rng.choice([f"trường: {rng.choice(SLOTS['schools'])}", "trường / nguyện vọng em vừa bỏ (không nói tên)"])
    if kind == "two_nganh":
        a, b = rng.sample(SLOTS["nganh"], 2)
        return f"hai ngành: {a}; {b}"
    if kind == "nganh":
        return f"ngành: {rng.choice(SLOTS['nganh'])}"
    if kind == "nv":
        return f"nguyện vọng số {rng.randint(1, 15)}"
    if kind == "school":
        return f"trường: {rng.choice(SLOTS['schools'])}"
    if kind == "level":
        return f"mức: {rng.choice(LEVELS)}"
    return ""

def build_prompt(rtype, rng):
    desc, kind = TYPES[rtype]
    attrs = {k: rng.choice(v) for k, v in ATTRIBUTES.items()}
    hint = slot_hint(kind, rng)
    seeds = "\n".join(f"- {s}" for s in SEEDS[rtype])
    prompt = (
        "Bạn giúp tạo dữ liệu huấn luyện cho chatbot của một ứng dụng tư vấn đăng ký nguyện vọng đại học ở Việt Nam. "
        f"Hãy viết đúng {MESSAGES_PER_PROMPT} tin nhắn khác nhau mà {attrs['writer']} có thể gõ vào khung chat, "
        f"mỗi tin nhắn chỉ có MỘT yêu cầu thuộc loại: {desc}.\n"
        f"Ví dụ về loại này:\n{seeds}\n"
        + (f"Dùng các giá trị sau (có thể viết tắt hoặc gọi theo cách thường nói): {hint}\n" if hint else "")
        + f"Phong cách: {attrs['register']}; {attrs['accents']}; {attrs['noise']}; độ dài: {attrs['length']}; "
        f"dạng: {attrs['form']}.\n"
        "Không lặp lại ví dụ. Không thêm yêu cầu thuộc loại khác. "
        "Chỉ trả về một mảng JSON gồm các chuỗi, không giải thích."
    )
    return prompt, attrs, hint

def parse(text):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [s.strip() for s in items if isinstance(s, str) and 2 <= len(s.strip()) <= 300]

def load(model_id, how):
    tok = AutoTokenizer.from_pretrained(model_id, token=os.environ.get("HF_TOKEN"))
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    kwargs = dict(device_map="auto", token=os.environ.get("HF_TOKEN"))
    if how == "fp16":
        kwargs["torch_dtype"] = torch.float16
    elif how == "4bit_fp32":
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                           bnb_4bit_compute_dtype=torch.float32)
        kwargs["attn_implementation"] = "eager"
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    model.eval()
    return tok, model

def chat_text(tok, prompt):
    messages = [{"role": "user", "content": prompt}]   # no system role: Gemma has none
    if tok.chat_template:
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    # Fallback when the tokenizer ships no template: SeaLLM-7B-v2's documented format (one BOS, no newline after </s>).
    return f"<s><|im_start|>user\n{prompt}</s><|im_start|>assistant\n"

def run_family(family):
    model_id, how = MODELS[family]
    rng = random.Random(f"{SEED}-{family}")
    jobs = []
    for rtype in (RUN_TYPES or TYPES):
        for k in range(PROMPTS_PER_TYPE):
            prompt, attrs, hint = build_prompt(rtype, rng)
            jobs.append((f"{family}-{rtype}-{k}", rtype, prompt, attrs, hint))
    tok, model = load(model_id, how)
    rows, start = [], time.time()
    for b in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[b:b + BATCH_SIZE]
        enc = tok([chat_text(tok, j[2]) for j in batch], return_tensors="pt", padding=True,
                  add_special_tokens=False).to(model.device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=MAX_NEW_TOKENS, do_sample=True, temperature=TEMPERATURE,
                                 top_p=TOP_P, pad_token_id=tok.pad_token_id)
        texts = tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        for (pid, rtype, prompt, attrs, hint), text in zip(batch, texts):
            for msg in parse(text):
                rows.append({"text": msg, "type": rtype, "family": family, "model": model_id,
                             "attributes": json.dumps({**attrs, "values": hint}, ensure_ascii=False),
                             "prompt_id": pid})
        if b % (BATCH_SIZE * 10) == 0:
            print(f"{family}: {b + len(batch)}/{len(jobs)} prompts, {len(rows)} messages, {time.time() - start:.0f}s")
    del model
    gc.collect()
    torch.cuda.empty_cache()
    df = pd.DataFrame(rows)
    tag = family if ROUND == 1 else f"{family}_round{ROUND}"
    df.to_csv(f"/kaggle/working/chat_generated_{tag}.csv", index=False)
    (df.groupby("type", group_keys=False).apply(lambda g: g.sample(min(20, len(g)), random_state=SEED))
       .to_csv(f"/kaggle/working/chat_review_sample_{tag}.csv", index=False))
    print(family, "done:", len(df), "messages")
    print(df["type"].value_counts())
    return df

results = {f: run_family(f) for f in RUN_FAMILIES}
"""

OUTRO = r"""## After the run

1. Download `chat_generated_<family>.csv` into `data/chat/generated/` and `chat_review_sample_<family>.csv` into
   `data/chat/review/` of the repository.
2. People read the review samples (spec 5: "People review generated messages") and mark wrong or unnatural messages.
3. `python -m uniadvisor.chat.train` trains on the training families, tests on the held-out family and on the people-
   judged check set, and writes `models/message_classifier/report.md`. The app switches from rules to the model only
   when the model reaches the targets in `config/chat.yaml` and beats the rules.
"""


def _cell(kind: str, source: str) -> dict:
    cell = {"cell_type": kind, "metadata": {}, "source": source.strip("\n").splitlines(keepends=True)}
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
    return cell


def slots() -> dict:
    d = AppData.load()
    schools = sorted({_short_school(n) for n in d.school_names.values()} |
                     {a for names in d.school_aliases.values() for a in names})
    nganh = sorted({d.catalog.label(c) for c in d.catalog.nganh_codes()} |
                   {p.strip() for c, m in d.catalog.majors.items() if m.level == "nhom_nganh" and m.display
                    for p in m.display.split(",") if 3 <= len(p.strip()) <= 40})
    return {"schools": schools, "nganh": nganh, "subjects": list(d.subjects.values())}


def _short_school(name: str) -> str:
    for prefix in ("Trường Đại học ", "Học viện ", "Trường "):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def build() -> dict:
    data_cell = ("SLOTS = " + json.dumps(slots(), ensure_ascii=False, indent=1) + "\n\nTYPES = "
                 + json.dumps(TYPES, ensure_ascii=False, indent=1) + "\n\nSEEDS = "
                 + json.dumps(SEEDS, ensure_ascii=False, indent=1) + "\n\nATTRIBUTES = "
                 + json.dumps(ATTRIBUTES, ensure_ascii=False, indent=1) + "\n")
    cells = [_cell("markdown", INTRO), _cell("code", CONFIG), _cell("code", INSTALL), _cell("code", LIBS),
             _cell("markdown", "## Names, request types, seed examples and attributes (from UniAdvisor's data)"),
             _cell("code", data_cell), _cell("markdown", "## Generation"), _cell("code", GENERATE),
             _cell("markdown", OUTRO)]
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                                        "name": "python3"},
                                         "language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
