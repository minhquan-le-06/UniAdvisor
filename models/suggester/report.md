# Major suggester: model report

Families: aya, gemma, mistral, qwen. Trained on 6689 kept students; tested on held-out family `mistral`. L2 = 0.3 (validation MRR by L2: {'0.03': 0.6056, '0.1': 0.614, '0.3': 0.6158, '1.0': 0.5948, '3.0': 0.5309}); data-score scale beta = 0.665.

| Test set | students | Hit@1 | Hit@5 | MRR | median rank |
|---|---|---|---|---|---|
| kept: data scores (baseline) | 648 | 6.6% | 26.4% | 0.188 | 11 |
| kept: model | 648 | 13.4% | 43.4% | 0.288 | 7 |
| all parsed: data scores (baseline) | 1077 | 4.4% | 17.1% | 0.131 | 22 |
| all parsed: model | 1077 | 9.3% | 31.8% | 0.216 | 12 |

Behaviour checks (31 hand-written cases, random answer sets, reachability):

| Check | data scores | model |
|---|---|---|
| hand-written cases passed | 28/31 | 31/31 |
| most frequent group in random top 5 | 16.8% | 23.0% |
| groups that cannot reach the top 5 | 4 | 0 |
| same answers, same order | True | True |

Ready for the app: **True** (beats the baseline and passes the checks).

Largest learned option weights (a label that nearly names a group should not dominate):

- q4 Nấu ăn -> Dinh dưỡng: +6.91
- q8 Khách sạn -> Du lịch, Quản trị dịch vụ du lịch và lữ hành: +5.97
- q8 Bệnh viện -> Nha khoa (Răng - Hàm - Mặt): +5.50
- q8 Bệnh viện -> Quản lý Y tế: +5.47
- q8 Công trường -> Quản lý xây dựng, Kinh tế xây dựng: +5.46
- q4 Vẽ -> Kiến trúc, Quy hoạch, Thiết kế nội thất: +5.40
- q6 Pháp luật -> Luật, Luật kinh tế, Luật quốc tế: +5.40
- q8 Khách sạn -> Quản trị khách sạn, nhà hàng: +5.10
- q1 Hóa học -> Hóa học, Vật lý học, Khoa học vật liệu: +5.06
- q6 Môi trường -> Công nghệ hóa học, môi trường, vật liệu: +5.00
- q1 Địa lí -> Địa lý học: +4.97
- q1 Hóa học -> Kỹ thuật môi trường, hóa học, vật liệu: +4.90
- q6 Môi trường -> Kỹ thuật môi trường, hóa học, vật liệu: +4.82
- q6 Môi trường -> Khoa học môi trường: +4.73
- q8 Bệnh viện -> Xét nghiệm, Hình ảnh y học, Phục hồi chức năng: +4.70
