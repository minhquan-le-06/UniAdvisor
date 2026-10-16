# Free-text reader report

Rules (config/free_text_reader.yaml), checked on the generated students' free texts: a guess counts as right when the student also ticked the option (a lower bound: writers mention things they did not tick).

Hand-written checks: 8/8.

| Family | texts | precision | texts with a guess | guesses per text |
|---|---|---|---|---|
| aya, all | 1688 | 68.5% | 99% | 3.90 |
| aya, subjects, topics, activities (q1-q7) | 1688 | 69.9% | 95% | 2.94 |
| aya, place and way of working (q8-q11) | 1688 | 72.3% | 52% | 0.71 |
| aya, conditions not wanted (q12) | 1688 | 40.5% | 16% | 0.25 |
| gemma, all | 1469 | 57.2% | 75% | 1.90 |
| gemma, subjects, topics, activities (q1-q7) | 1469 | 61.2% | 63% | 1.34 |
| gemma, place and way of working (q8-q11) | 1469 | 70.5% | 27% | 0.33 |
| gemma, conditions not wanted (q12) | 1469 | 15.6% | 20% | 0.24 |
| mistral, all | 484 | 37.7% | 97% | 6.26 |
| mistral, subjects, topics, activities (q1-q7) | 484 | 42.8% | 79% | 3.18 |
| mistral, place and way of working (q8-q11) | 484 | 49.6% | 53% | 1.46 |
| mistral, conditions not wanted (q12) | 484 | 17.2% | 78% | 1.62 |
| qwen, all | 1840 | 60.7% | 94% | 3.34 |
| qwen, subjects, topics, activities (q1-q7) | 1840 | 68.5% | 83% | 2.19 |
| qwen, place and way of working (q8-q11) | 1840 | 71.9% | 39% | 0.61 |
| qwen, conditions not wanted (q12) | 1840 | 17.3% | 33% | 0.55 |

Hand-written texts (drafted checks): expected options, and what the reader found.

- ok: "em thích vẽ và chụp ảnh, sau này muốn làm thiết kế" -> q4 Vẽ, q4 Chụp ảnh
- ok: "em rất ghét máu, không muốn làm trong bệnh viện" -> q12 Thấy máu
- ok: "em thich lap trinh va giai toan kho" -> q4 Viết code, q4 Giải bài toán khó
- ok: "em muốn đi làm ở văn phòng, không thích làm ngoài trời" -> q12 Làm việc ngoài trời, q8 Văn phòng
- ok: "mình thích nấu ăn với chăm sóc con vật" -> q4 Chăm sóc con vật, q4 Nấu ăn
- ok: "em thích kinh tế, muốn sau này quản lý doanh nghiệp" -> q6 Quản lý doanh nghiệp, q6 Kinh tế
- ok: "em học tốt toán nhưng không thích hóa học" -> q1 Toán, q2 Hóa học
- ok: "sở thích của em là đọc truyện và viết về lịch sử" -> q1 Lịch sử, q5 Đọc tiểu thuyết, q6 Lịch sử
