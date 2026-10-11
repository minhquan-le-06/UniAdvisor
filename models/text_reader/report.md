# Free-text reader report

Rules (config/free_text_reader.yaml), checked on the generated students' free texts: a guess counts as right when the student also ticked the option (a lower bound: writers mention things they did not tick).

Hand-written checks: 8/8.

| Family | texts | precision | texts with a guess | guesses per text |
|---|---|---|---|---|
| aya, all | 1712 | 68.7% | 98% | 3.90 |
| aya, subjects, topics, activities (q1-q7) | 1712 | 70.1% | 95% | 2.94 |
| aya, place and way of working (q8-q11) | 1712 | 72.5% | 53% | 0.71 |
| aya, conditions not wanted (q12) | 1712 | 40.5% | 16% | 0.25 |
| gemma, all | 518 | 54.1% | 78% | 1.86 |
| gemma, subjects, topics, activities (q1-q7) | 518 | 59.3% | 66% | 1.31 |
| gemma, place and way of working (q8-q11) | 518 | 71.6% | 25% | 0.30 |
| gemma, conditions not wanted (q12) | 518 | 7.5% | 21% | 0.26 |
| mistral, all | 496 | 37.7% | 97% | 6.30 |
| mistral, subjects, topics, activities (q1-q7) | 496 | 42.7% | 78% | 3.20 |
| mistral, place and way of working (q8-q11) | 496 | 49.7% | 53% | 1.46 |
| mistral, conditions not wanted (q12) | 496 | 17.1% | 78% | 1.63 |
| qwen, all | 1879 | 60.6% | 94% | 3.34 |
| qwen, subjects, topics, activities (q1-q7) | 1879 | 68.2% | 83% | 2.19 |
| qwen, place and way of working (q8-q11) | 1879 | 72.0% | 39% | 0.60 |
| qwen, conditions not wanted (q12) | 1879 | 17.3% | 33% | 0.54 |

Hand-written texts (drafted checks): expected options, and what the reader found.

- ok: "em thích vẽ và chụp ảnh, sau này muốn làm thiết kế" -> q4 Vẽ, q4 Chụp ảnh
- ok: "em rất ghét máu, không muốn làm trong bệnh viện" -> q12 Thấy máu
- ok: "em thich lap trinh va giai toan kho" -> q4 Viết code, q4 Giải bài toán khó
- ok: "em muốn đi làm ở văn phòng, không thích làm ngoài trời" -> q12 Làm việc ngoài trời, q8 Văn phòng
- ok: "mình thích nấu ăn với chăm sóc con vật" -> q4 Chăm sóc con vật, q4 Nấu ăn
- ok: "em thích kinh tế, muốn sau này quản lý doanh nghiệp" -> q6 Quản lý doanh nghiệp, q6 Kinh tế
- ok: "em học tốt toán nhưng không thích hóa học" -> q1 Toán, q2 Hóa học
- ok: "sở thích của em là đọc truyện và viết về lịch sử" -> q1 Lịch sử, q5 Đọc tiểu thuyết, q6 Lịch sử
