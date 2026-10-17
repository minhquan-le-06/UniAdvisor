// The explanations behind the "?" next to khu vực ưu tiên and đối tượng ưu tiên. Source: Quy chế tuyển sinh đại học
// năm 2026 (Phụ lục I khu vực, Phụ lục II đối tượng), as summarised at
// https://xaydungchinhsach.chinhphu.vn/chinh-sach-uu-tien-trong-tuyen-sinh-dai-hoc-119260227153842885.htm
import type { ReactNode } from "react";

const SOURCE = "Theo Quy chế tuyển sinh đại học năm 2026. Em xem thông báo của từng trường để chắc chắn.";

export const HELP: Record<"area" | "category", { title: string; body: ReactNode }> = {
  area: {
    title: "Khu vực ưu tiên là gì?",
    body: (
      <>
        <p>Là điểm cộng theo nơi em học THPT, không phải nơi em ở. Khu vực tính theo trường em học lâu nhất; học bằng nhau thì lấy trường học sau cùng. Em được hưởng trong năm tốt nghiệp và một năm kế tiếp.</p>
        <ul>
          <li><strong>KV1 (+0,75):</strong> vùng đồng bào dân tộc thiểu số, miền núi, hải đảo, biên giới đất liền, xã khó khăn.</li>
          <li><strong>KV2-NT (+0,50):</strong> các địa phương không thuộc KV1, KV2, KV3.</li>
          <li><strong>KV2 (+0,25):</strong> phường thuộc tỉnh; xã của thành phố trực thuộc Trung ương (trừ xã KV1).</li>
          <li><strong>KV3 (không cộng):</strong> phường của thành phố trực thuộc Trung ương.</li>
        </ul>
        <p>Chọn trường ở câu trên thì ứng dụng điền khu vực giúp em. Điểm đạt từ 22,5 trở lên thì điểm ưu tiên được giảm dần theo quy chế.</p>
        <p className="muted">{SOURCE}</p>
      </>
    ),
  },
  category: {
    title: "Đối tượng ưu tiên là gì?",
    body: (
      <>
        <p>Là điểm cộng theo đối tượng chính sách. Em thuộc nhiều diện thì chỉ được hưởng một mức cao nhất.</p>
        <ul>
          <li><strong>Ưu tiên 1 (+2,00), đối tượng 01 đến 03:</strong> người dân tộc thiểu số được hưởng KV1; thương binh, bệnh binh, quân nhân và công an nghĩa vụ đã xuất ngũ; thân nhân liệt sĩ, con thương binh, bệnh binh hoặc người nhiễm chất độc hóa học suy giảm từ 81%, con Anh hùng.</li>
          <li><strong>Ưu tiên 2 (+1,00), đối tượng 04 đến 06:</strong> thanh niên xung phong, quân nhân và công an tại ngũ được cử đi học (phục vụ trên 15 tháng); người dân tộc thiểu số học ngoài khu vực; con thương binh, bệnh binh suy giảm dưới 81%; người khuyết tật nặng; giáo viên hoặc cán bộ y tế đủ 3 năm công tác dự tuyển đúng lĩnh vực.</li>
        </ul>
        <p>Không chắc thì chọn “Không thuộc đối tượng ưu tiên”; em sửa lại sau cũng được.</p>
        <p className="muted">{SOURCE}</p>
      </>
    ),
  },
};
