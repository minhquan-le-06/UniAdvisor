"""The review archive (data/reviews/): rounds appended per kind, nothing lost."""

import pandas as pd
import pytest

from uniadvisor.reviews import archive_round


def test_rounds_are_appended_per_kind(tmp_path):
    r1 = tmp_path / "step6_llm_2026-10-07"
    r1.mkdir()
    (r1 / "nganh_close_review_done.csv").write_text("nganh_code,other_code,verdict\n7480101,7480201,ok\n",
                                                    encoding="utf-8-sig")
    (r1 / "riasec_names_vi_done.csv").write_text("riasec,verdict\nSocial,ok\n", encoding="utf-8")
    (r1 / "review_summary.md").write_text("# notes\n", encoding="utf-8")
    r2 = tmp_path / "close_owner_2026-10-08"
    r2.mkdir()
    (r2 / "nganh_close_review_done.csv").write_text("nganh_code,other_code,verdict,comment\n7480101,7480103,weak,x\n",
                                                    encoding="utf-8")
    assert archive_round(r1, tmp_path) == {"nganh_close_review.csv": 1, "names_vi_review.csv": 1}
    archive_round(r2, tmp_path)
    assert not r1.exists() and not r2.exists()
    close = pd.read_csv(tmp_path / "nganh_close_review.csv", dtype=str, keep_default_na=False)
    assert list(close.columns) == ["round", "nganh_code", "other_code", "verdict", "comment"]
    assert close.to_dict("records") == [
        {"round": "step6_llm_2026-10-07", "nganh_code": "7480101", "other_code": "7480201", "verdict": "ok",
         "comment": ""},
        {"round": "close_owner_2026-10-08", "nganh_code": "7480101", "other_code": "7480103", "verdict": "weak",
         "comment": "x"}]
    names = pd.read_csv(tmp_path / "names_vi_review.csv", dtype=str, keep_default_na=False)
    assert names.iloc[0][["round", "kind", "riasec"]].tolist() == ["step6_llm_2026-10-07", "riasec", "Social"]
    assert (tmp_path / "summaries" / "step6_llm_2026-10-07.md").read_text(encoding="utf-8") == "# notes\n"
    again = tmp_path / "close_owner_2026-10-08"                 # the same round twice is refused
    again.mkdir()
    (again / "nganh_close_review_done.csv").write_text("nganh_code,other_code,verdict\n1,2,ok\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        archive_round(again, tmp_path)
