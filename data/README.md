# data/

Ứng dụng đọc một cơ sở dữ liệu SQLite duy nhất, `data/uniadvisor.db` (khoảng 29 MB). **File này không có trong repo nộp BTC**: nó chứa điểm chuẩn, học phí và thông tin chương trình thu thập từ các trang tin công khai và tài liệu của các trường.

- **Bản web** ([uniadvisor-bkq.vercel.app](https://uniadvisor-bkq.vercel.app/)) không dựng cơ sở dữ liệu: khi khởi động, máy chủ tải file này từ một dataset riêng tư trên Hugging Face.
- **Chạy cục bộ** cần có sẵn `uniadvisor.db` (đặt ở đây hoặc trỏ biến `UNIADVISOR_DB` tới nó). Trong repo nộp BTC, các bảng đầu vào đã bị lược bỏ nên không thể tự dựng lại; cách dựng được mô tả ở [`pipelines/README.md`](../pipelines/README.md).
- **Bộ test** không cần dữ liệu thật: chúng chạy trên một cơ sở dữ liệu giả nhỏ dựng ngay trong test (`tests/fakedb.py`).
