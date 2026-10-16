import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { fold } from "./Combobox";
import { format } from "./NumberField";
import { Pentagon } from "./Pentagon";
import { PillGroup } from "./Pill";

function Multi({ max }: { max: number }) {
  const [v, setV] = useState<string[]>([]);
  return <PillGroup mode="multi" label="Môn" max={max} value={v} onChange={setV}
                    options={["a", "b", "c"].map((x) => ({ value: x, label: x.toUpperCase() }))} />;
}

describe("PillGroup", () => {
  it("stops at the cap and greys out the rest", async () => {
    render(<Multi max={2} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox", { name: "A" }));
    await user.click(screen.getByRole("checkbox", { name: "B" }));
    expect(screen.getByRole("checkbox", { name: "A" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("checkbox", { name: "C" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "A" }));
    expect(screen.getByRole("checkbox", { name: "C" })).toBeEnabled();
  });
});

describe("Pentagon", () => {
  it("leaves out a corner without data and says so", () => {
    const { container } = render(
      <Pentagon series={[{ label: "X", color: "red", values: { hop_mon: 0.5, nguyen_vong_cao: 0.2, dung_nganh: 1, hoc_phi: 0.4, nghe_nghiep: null } }]} />,
    );
    expect(container.querySelectorAll("circle")).toHaveLength(4);
    expect(container.querySelectorAll("polygon").length).toBe(5);       // 4 grid rings + the shape
    expect(screen.getByText("chưa có dữ liệu")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("draws no shape with fewer than three known corners", () => {
    const { container } = render(<Pentagon series={[{ label: "X", color: "red", values: { hop_mon: 0.5, dung_nganh: 1 } }]} />);
    expect(container.querySelectorAll("polygon").length).toBe(4);       // grid only
  });
});

describe("text helpers", () => {
  it("searches without accents", () => {
    expect(fold("Đại học Bách khoa Hà Nội")).toBe("dai hoc bach khoa ha noi");
  });
  it("writes Vietnamese decimals", () => {
    expect(format(8.5)).toBe("8,5");
    expect(format(null)).toBe("");
  });
});
