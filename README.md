<div align="center">

# 🧭 UniAdvisor

**Chọn ngành, xếp 15 nguyện vọng đại học trong 10 phút**

*Trợ lý cho học sinh lớp 12 ở Hà Nội và TP.HCM, xét bằng điểm thi tốt nghiệp THPT*

[![Demo](https://img.shields.io/badge/%F0%9F%9A%80_Demo_tr%E1%BB%B1c_ti%E1%BA%BFp-uniadvisor--bkq.vercel.app-ff6b4a?style=for-the-badge)](https://uniadvisor-bkq.vercel.app/)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-ffc83d)

</div>

> [!IMPORTANT]
> **Repo này chỉ dùng để nộp cho BTC (MLAI Hackathon 2026), không dùng để chạy demo.**
> Cơ sở dữ liệu (`uniadvisor.db`) và dữ liệu thô đã được lược bỏ khỏi repo, nên ứng dụng không chạy được từ đây.
> Hãy dùng bản chạy sẵn: **[uniadvisor-bkq.vercel.app](https://uniadvisor-bkq.vercel.app/)**
> (lần mở đầu có thể chậm vài giây vì máy chủ phải nạp dữ liệu).

## ✨ UniAdvisor làm được gì

| Bước | Em làm gì |
|---|---|
| 1️⃣ **Về em** | Nhập điểm dự kiến hoặc điểm thi thật, tỉnh/thành, khu vực và đối tượng ưu tiên, ngân sách. |
| 2️⃣ **Chọn ngành** | Đã có ngành thì tìm và so sánh; chưa biết chọn gì thì trả lời 12 câu hỏi để nhận gợi ý nhóm ngành kèm lý do. |
| 3️⃣ **Xếp hướng học** | Chọn tối đa 2 hướng học, mỗi hướng gồm một ngành chính và các ngành gần. |
| 🎯 **Ba phương án** | Nhận 3 danh sách 15 nguyện vọng: *Đúng ngành nhất*, *Hợp sở thích nhất*, *Tiết kiệm nhất*, so sánh bằng biểu đồ năm góc. |
| 💬 **Điều chỉnh** | Chọn một phương án rồi chỉnh bằng nút hoặc chat tiếng Việt; tải kế hoạch về máy để dùng lại sau kỳ thi. |

Mỗi nguyện vọng ghi rõ mức (mơ ước, thử sức, vừa sức, an toàn), điểm xét tuyển của em, điểm chuẩn 2025 và 2026, học phí và nơi học.

## 🧠 Quy tắc quyết định, AI chỉ hỗ trợ

- **Thứ tự nguyện vọng do luật cố định, kiểm thử được:** điểm xét tuyển từng chương trình (kèm điểm ưu tiên theo Thông tư 06/2026/TT-BGDĐT) được so với điểm chuẩn hai năm gần nhất để chia bốn mức mơ ước, thử sức, vừa sức, an toàn; nguyện vọng an toàn xếp cuối. Biểu đồ năm góc của mỗi phương án được ước tính bằng mô phỏng Monte Carlo 20.000 lần.
- **Hai mô hình nhỏ chạy trên CPU:** một mô hình gợi ý nhóm ngành từ bộ câu hỏi, một bộ phân loại câu chat thành 28 loại yêu cầu.
- **Không gọi LLM hay dịch vụ ngoài khi chạy.** Mọi câu chữ em đọc đều từ mẫu cố định điền dữ liệu thật.
- **Riêng tư:** thông tin em nhập nằm ở trình duyệt, máy chủ không lưu và không ghi log; kế hoạch được tải thẳng về máy em.

Kết quả trên dữ liệu chưa dùng khi huấn luyện (dòng mô hình Mistral):

| Đánh giá | Cơ sở so sánh | Mô hình | Cỡ tập |
|---|---|---|---|
| Gợi ý nhóm ngành, Hit@5 | 51,5% | **64,2%** | 648 |
| Gợi ý nhóm ngành, Hit@1 | 19,4% | **26,4%** | 648 |
| 31 tình huống kiểm thử hành vi (viết tay) | 28/31 | **31/31** | 31 |
| Phân loại tin nhắn, macro-F1 | 0,641 | **0,881** | 1.361 |
| Phân loại tin nhắn, macro-F1 sau khi loại tin sai nhãn | 0,715 | **0,970** | 847 |
| Phân loại tin nhắn, độ chính xác (190 tin có người rà soát) | 0,921 | **0,926** | 190 |

Hit@k: nhóm ngành mục tiêu (hoặc nhóm gần) có trong top k gợi ý. Hệ thống chưa được đánh giá trên học sinh thật.

Chi tiết: [báo cáo bộ gợi ý](models/suggester/report.md) · [báo cáo bộ phân loại](models/message_classifier/report.md) · [pipelines](pipelines/README.md)

## 🗂️ Cấu trúc repo

| Đường dẫn | Nội dung |
|---|---|
| [`web/`](web) | Giao diện (Vite, React, TypeScript) |
| [`src/uniadvisor/api/`](src/uniadvisor/api) | API FastAPI không lưu trạng thái |
| [`src/uniadvisor/planner/`](src/uniadvisor/planner) | Luật lập danh sách, ba phương án, biểu đồ năm góc |
| [`src/uniadvisor/majors/`](src/uniadvisor/majors) | Bộ câu hỏi và gợi ý nhóm ngành |
| [`src/uniadvisor/chat/`](src/uniadvisor/chat) | Chat: tách câu, phân loại, trích giá trị, trả lời |
| [`config/`](config) · [`models/`](models) | Luật tuyển sinh theo năm, cấu hình, mô hình đã huấn luyện |
| [`pipelines/`](pipelines) | Công cụ dựng cơ sở dữ liệu và huấn luyện mô hình (ngoài ứng dụng) |
| [`tests/`](tests) | 600 test, chạy trên cơ sở dữ liệu giả |
| [`app.py`](app.py) · [`web_api.py`](web_api.py) · [`vercel.json`](vercel.json) · [`Dockerfile`](Dockerfile) | Bản Streamlit cũ, điểm vào API, cấu hình Vercel và Docker |

Chạy bộ test (không cần dữ liệu thật): `pip install -e ".[dev,ui]"` rồi `python -m pytest`; phía giao diện: `npm --prefix web ci && npm --prefix web test`.

## 📚 Nguồn dữ liệu và ghi nhận

| Chỉ số (tính đến 16/10/2026) | Giá trị |
|---|---|
| Trường trong phạm vi | **159** (98 Hà Nội, 61 TP.HCM) |
| Chương trình | **3.874** thuộc 374 ngành; 3.843 đủ dữ liệu để lập danh sách |
| Có điểm chuẩn cả 2025 và 2026 | 2.500 chương trình |
| Có dữ liệu học phí | 87% |
| Tỷ lệ sinh viên có việc làm | 529 dòng của 26 trường |

Điểm chuẩn lấy từ các trang tin công khai ([VnExpress](https://vnexpress.net), [Tuyensinh247](https://tuyensinh247.com), [VietNamNet](https://vietnamnet.vn)) và tài liệu của chính các trường (ưu tiên khi hai nguồn khác nhau); danh mục ngành theo Thông tư 09/2022/TT-BGDĐT.

> Sản phẩm này có dùng thông tin từ [O\*NET 31.0 Database](https://www.onetcenter.org/database.html) của U.S. Department of Labor, Employment and Training Administration (USDOL/ETA), theo giấy phép [CC BY 4.0](https://www.onetcenter.org/license_db.html). UniAdvisor đã chỉnh sửa thông tin (chọn lọc, dịch sang tiếng Việt, tổng hợp theo ngành). USDOL/ETA không phê duyệt, bảo trợ hay kiểm tra các chỉnh sửa này.

Dữ liệu huấn luyện (học sinh và tin nhắn giả lập) do ba dòng mô hình mở Qwen 2.5, Aya Expanse, Gemma 2 viết (6.689 hồ sơ sau khi làm sạch); dòng thứ tư, Mistral (SeaLLM-7B-v2), chỉ dùng để kiểm thử. Theo giấy phép của từng mô hình.

---

<div align="center">

Làm cho **MLAI Hackathon 2026** (TMA, Decision Intelligence Challenge) · Giấy phép mã nguồn: [MIT](LICENSE)

</div>
