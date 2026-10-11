# Major suggester: model report

Families: aya, gemma, mistral, qwen. Trained on 5519 kept students; tested on held-out family `mistral`. L2 = 0.1 (validation MRR by L2: {'0.03': 0.6129, '0.1': 0.623, '0.3': 0.6217, '1.0': 0.6021, '3.0': 0.5278}); data-score scale beta = 0.735.

| Test set | students | Hit@1 | Hit@5 | MRR | median rank |
|---|---|---|---|---|---|
| kept: data scores (baseline) | 656 | 6.6% | 26.5% | 0.189 | 11 |
| kept: model | 656 | 13.3% | 43.4% | 0.277 | 8 |
| all parsed: data scores (baseline) | 1077 | 4.4% | 17.5% | 0.133 | 20 |
| all parsed: model | 1077 | 9.5% | 32.7% | 0.214 | 12 |

Behaviour checks (31 hand-written cases, random answer sets, reachability):

| Check | data scores | model |
|---|---|---|
| hand-written cases passed | 28/31 | 31/31 |
| most frequent group in random top 5 | 16.9% | 21.1% |
| groups that cannot reach the top 5 | 2 | 0 |
| same answers, same order | True | True |

Ready for the app: **True** (beats the baseline and passes the checks).

Largest learned option weights (a label that nearly names a group should not dominate):

- q4 Nấu ăn -> Dinh dưỡng: +9.87
- q4 Vẽ -> Kiến trúc, Quy hoạch, Thiết kế nội thất: +8.45
- q8 Khách sạn -> Du lịch, Quản trị dịch vụ du lịch và lữ hành: +8.05
- q4 Nấu ăn -> Công nghệ thực phẩm: +7.53
- q8 Bệnh viện -> Nha khoa (Răng - Hàm - Mặt): +7.42
- q8 Bệnh viện -> Quản lý Y tế: +7.37
- q6 Môi trường -> Công nghệ hóa học, môi trường, vật liệu: +7.18
- q6 Pháp luật -> Luật, Luật kinh tế, Luật quốc tế: +7.13
- q1 Địa lí -> Địa lý học: +7.12
- q1 Hóa học -> Kỹ thuật môi trường, hóa học, vật liệu: +6.94
- q4 Sửa chữa đồ đạc -> Kỹ thuật cơ khí, cơ điện tử, ô tô: +6.94
- q4 Nấu ăn -> Quản trị khách sạn, nhà hàng: +6.94
- q8 Khách sạn -> Quản trị khách sạn, nhà hàng: +6.90
- q8 Công trường -> Quản lý xây dựng, Kinh tế xây dựng: +6.84
- q6 Môi trường -> Kỹ thuật môi trường, hóa học, vật liệu: +6.83
