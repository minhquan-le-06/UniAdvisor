# pipelines/

Các công cụ chạy ngoài ứng dụng, tạo ra những gì ứng dụng đọc: cơ sở dữ liệu (`data/uniadvisor.db`) và hai mô hình trong [`models/`](../models). Ứng dụng đang chạy không import chúng. Chạy mọi lệnh từ thư mục gốc của repo.

> **Lưu ý về repo nộp BTC:** dữ liệu thô (trang đã lưu, tài liệu của các trường, bảng đã rà soát, dữ liệu huấn luyện do LLM sinh) và các bảng cuối `pipelines/data/tables/` **không được công bố**, nên các lệnh dựng cơ sở dữ liệu và huấn luyện bên dưới không chạy được từ đây. Mã nguồn được giữ lại để mọi con số trong ứng dụng đều truy ngược được cách tạo ra; bộ test chạy phần dựng trên một bộ dữ liệu mẫu nhỏ cùng định dạng (`tests/rawfixture.py`).

## Cơ sở dữ liệu

| Lệnh | Việc làm |
|---|---|
| `python -m pipelines.collect.run` | Thu thập điểm chuẩn đã công bố của các trường trong phạm vi từ các trang công khai, qua bộ nhớ đệm (`--offline` chỉ dựng lại từ bộ nhớ đệm) |
| `python -m pipelines.database.prepare` | Bước chậm (vài phút): áp dụng các quy tắc lên dữ liệu thô và các chỉnh sửa đã rà soát, ghi các bảng cuối (mỗi bảng một CSV, đúng cột của bảng CSDL) vào `pipelines/data/tables/`, cùng `data/coverage.md` và danh sách rà soát trong `data/review/`. `--check` cho biết các bảng đã lỗi thời chưa |
| `python -m pipelines.database.build` | Nạp các bảng cuối vào `data/uniadvisor.db` trong vài giây: trường, chương trình, tổ hợp xét tuyển, điểm chuẩn quy về thang 30, học phí, mã ngành của Bộ GD&ĐT và thông tin từng ngành |
| `python -m pipelines.database.compare OLD.db NEW.db` | So sánh hai cơ sở dữ liệu theo từng bảng: giá trị, kiểu và thứ tự dòng |
| `python -m pipelines.database.export` | Xuất các bảng của một cơ sở dữ liệu đã dựng ra thư mục CSV |
| `python -m pipelines.facts.sheets check` | Đối chiếu các tờ thông tin nhóm ngành đã duyệt với số liệu trong cơ sở dữ liệu |
| `python -m pipelines.facts.apply_review <thư mục>` | Áp dụng một vòng rà soát việc ghép ngành với nghề và ngành gần |

Mỗi quy tắc khi dựng đều có tên và được ghi trên dòng bị ảnh hưởng. Thứ tự ưu tiên nguồn: tài liệu của chính trường, rồi VnExpress, Tuyensinh247, VietNamNet. Thông tin từng ngành lấy từ O\*NET 31.0 qua bảng đối chiếu CIP 2020 sang O\*NET-SOC ([`pipelines/facts/`](facts)).

## Bộ gợi ý nhóm ngành ([`models/suggester/`](../models/suggester))

| Lệnh | Việc làm |
|---|---|
| `python -m pipelines.majors_model.make_notebook` | Tạo `pipelines/notebooks/student_generation*.ipynb`: các LLM mở chạy trên Kaggle viết ra học sinh giả lập trả lời bộ câu hỏi, mỗi hồ sơ được lập kế hoạch cho một nhóm ngành mục tiêu (sinh dữ liệu có điều kiện theo thuộc tính) |
| `python -m pipelines.majors_model.prepare` | Làm sạch các hồ sơ đã sinh (`pipelines/data/students/`) và viết báo cáo |
| `python -m pipelines.majors_model.train` | Học các trọng số lựa chọn nhỏ trên nền điểm cơ sở từ dữ liệu O\*NET, kiểm thử trên dòng LLM giữ riêng khỏi huấn luyện, chạy các kiểm tra hành vi và ghi `models/suggester/` |
| `python -m pipelines.majors_model.checks` | Kiểm tra hành vi của riêng điểm cơ sở (mức so sánh) |

## Bộ phân loại tin nhắn ([`models/message_classifier/`](../models/message_classifier))

Bộ phân loại học máy nhận diện 19 trong 28 loại yêu cầu; 9 loại còn lại (các câu hỏi về dữ liệu và phạm vi ở Phần 4) do bộ luật cố định xử lý cho đến khi huấn luyện lại.

| Lệnh | Việc làm |
|---|---|
| `python -m pipelines.chat_model.make_notebook` | Tạo `pipelines/notebooks/chat_message_generation.ipynb`: các LLM mở viết tin nhắn tiếng Việt cho từng loại yêu cầu (vòng 3 là chín loại mới của Phần 4) |
| `python -m pipelines.chat_model.train` | TF-IDF và hồi quy logistic trên các tin nhắn đã sinh; kiểm thử trên dòng LLM giữ riêng, bộ kiểm tra có người rà soát và tập giữ riêng do người viết của Phần 4 (nếu có). Mô hình chỉ được thay khi qua cả cổng kiểm tra Phần 4, nếu không chỉ ghi `candidate.joblib` |

## Đánh giá quy tắc lập danh sách

| Lệnh | Việc làm |
|---|---|
| `python -m pipelines.benchmarks.bench` | Luật lập danh sách trên 272 học sinh giả định (17 danh sách hướng học, tổng 15–29 nguyện vọng, hai thành phố) → `data/bench.md` |
| `python -m pipelines.benchmarks.bench_lists` | Ba phương án cho cùng nhóm học sinh → `data/bench_lists.md` |
| `python -m pipelines.benchmarks.samples` | Danh sách của vài học sinh mẫu để đọc → `data/sample_lists.md` |
