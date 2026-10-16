"""The request types the chat understands. One message may hold several requests; each request has one type.

Change types only change inputs (the fixed strategy then rebuilds the list); question types are answered from our data
with templates. Anything else is OTHER, and the chat replies with what it can do.
"""

CHANGE_TYPES = [
    "change_score",        # change a subject score
    "change_priority",     # change area (khu vực) or category (đối tượng)
    "change_budget",       # change the tuition budget
    "change_near_home",    # turn "học gần nhà" on or off
    "extra_points",        # enter extra points for a school
    "favorite_school",     # choose (or drop) the student's favorite school (added 2026-10-08)
    "own_score",           # the student's own admission score at a school, on its scale (added 2026-10-08)
    "cutoff_shift",        # a school's cutoffs are really higher / lower for the student (added 2026-10-08)
    "remove",              # remove a school (all its programs) or one wish
    "restore",             # bring a removed school or wish back
    "rerank",              # swap the 2 shortlist items
    "replace_nganh",       # replace a shortlist item, or swap a close ngành
    "undo",                # undo the last change
]

QUESTION_TYPES = [
    "ask_why_nv",          # why is this program at NV n
    "ask_why_not",         # why isn't school / program X on my list
    "ask_compare",         # difference between ngành A and B
    "ask_what_is",         # what is ngành A (study, jobs, strong subjects)
    "ask_level",           # what does this level mean
]

OTHER = "other"
# Types added after the classifier's first training run: the rules decide them until the model is retrained.
LATE_TYPES = ["favorite_school", "own_score", "cutoff_shift"]
ALL_TYPES = CHANGE_TYPES + QUESTION_TYPES + [OTHER]

TYPE_VI = {
    "change_score": "đổi điểm môn", "change_priority": "đổi khu vực / đối tượng ưu tiên",
    "change_budget": "đổi ngân sách học phí", "change_near_home": "bật / tắt học gần nhà",
    "extra_points": "nhập điểm cộng của một trường", "favorite_school": "chọn trường yêu thích nhất",
    "own_score": "nhập điểm xét tuyển em tự tính ở một trường",
    "cutoff_shift": "điều chỉnh điểm chuẩn của một trường cho riêng em",
    "remove": "bỏ một trường hoặc một nguyện vọng",
    "restore": "đưa lại trường hoặc nguyện vọng đã bỏ", "rerank": "đổi thứ tự hai lựa chọn",
    "replace_nganh": "thay lựa chọn hoặc ngành gần", "undo": "hoàn tác thay đổi gần nhất",
    "ask_why_nv": "hỏi vì sao một chương trình ở NV đó", "ask_why_not": "hỏi vì sao một trường không có trong danh sách",
    "ask_compare": "hỏi hai ngành khác nhau thế nào", "ask_what_is": "hỏi một ngành học gì",
    "ask_level": "hỏi một mức nghĩa là gì", "other": "khác",
}

# Shown when a request has no type: what the chat can do, with examples.
EXAMPLES_VI = [
    "Toán em được 8,5",
    "Em ở KV2-NT, đối tượng ưu tiên 2",
    "Ngân sách 40 triệu một năm",
    "Không cần học gần nhà nữa",
    "Trường Ngoại thương cộng cho em 1,5 điểm",
    "Trường em thích nhất là Bách khoa Hà Nội",
    "Điểm xét tuyển của em ở Bách khoa TP.HCM là 82",
    "Điểm chuẩn trường Công nghệ thông tin thực ra thấp hơn 1 điểm",
    "Bỏ trường Bách khoa Hà Nội; bỏ NV7",
    "Đưa Bách khoa Hà Nội trở lại",
    "Đổi thứ tự hai lựa chọn",
    "Thay ngành gần Marketing bằng Logistics",
    "Hoàn tác",
    "Vì sao NV3 lại ở đó?",
    "Sao không có trường Kinh tế Quốc dân?",
    "Khoa học máy tính với Công nghệ thông tin khác gì nhau?",
    "Ngành Logistics học gì?",
    "Thử sức nghĩa là gì?",
]
