# Message classifier report

Written 2026-10-08 by `python -m pipelines.chat_model.train`.

## Rule baseline (runtime fallback)

### Check set, all rows (LLM-drafted, not yet judged by people)

190 messages: accuracy 0.9211, macro-F1 0.926.

| type | F1 |
|---|---|
| ask_compare | 0.889 |
| ask_level | 0.9 |
| ask_what_is | 1.0 |
| ask_why_not | 0.947 |
| ask_why_nv | 0.947 |
| change_budget | 1.0 |
| change_near_home | 1.0 |
| change_priority | 0.947 |
| change_score | 0.952 |
| cutoff_shift | 1.0 |
| extra_points | 0.947 |
| favorite_school | 1.0 |
| other | 0.667 |
| own_score | 1.0 |
| remove | 0.889 |
| replace_nganh | 0.87 |
| rerank | 0.889 |
| restore | 0.75 |
| undo | 1.0 |

Most frequent mistakes (true -> predicted): restore -> other: 3; remove -> replace_nganh: 2; rerank -> other: 2; ask_compare -> other: 2; change_priority -> other: 1; extra_points -> other: 1; restore -> replace_nganh: 1; ask_why_nv -> ask_level: 1.

### Check set, rows people judged

190 messages: accuracy 0.9211, macro-F1 0.926.

| type | F1 |
|---|---|
| ask_compare | 0.889 |
| ask_level | 0.9 |
| ask_what_is | 1.0 |
| ask_why_not | 0.947 |
| ask_why_nv | 0.947 |
| change_budget | 1.0 |
| change_near_home | 1.0 |
| change_priority | 0.947 |
| change_score | 0.952 |
| cutoff_shift | 1.0 |
| extra_points | 0.947 |
| favorite_school | 1.0 |
| other | 0.667 |
| own_score | 1.0 |
| remove | 0.889 |
| replace_nganh | 0.87 |
| rerank | 0.889 |
| restore | 0.75 |
| undo | 1.0 |

Most frequent mistakes (true -> predicted): restore -> other: 3; remove -> replace_nganh: 2; rerank -> other: 2; ask_compare -> other: 2; change_priority -> other: 1; extra_points -> other: 1; restore -> replace_nganh: 1; ask_why_nv -> ask_level: 1.

### Held-out LLM family, after the LLM review

847 messages: accuracy 0.7037, macro-F1 0.715.

| type | F1 |
|---|---|
| ask_compare | 0.712 |
| ask_level | 0.739 |
| ask_what_is | 0.579 |
| ask_why_not | 0.765 |
| ask_why_nv | 0.926 |
| change_budget | 0.981 |
| change_near_home | 0.818 |
| change_priority | 0.907 |
| change_score | 0.811 |
| cutoff_shift | 0.222 |
| extra_points | 0.923 |
| favorite_school | 0.75 |
| other | 0.432 |
| remove | 0.679 |
| replace_nganh | 0.687 |
| rerank | 0.913 |
| restore | 0.51 |
| undo | 0.515 |

Most frequent mistakes (true -> predicted): undo -> other: 41; restore -> other: 40; remove -> replace_nganh: 20; ask_why_not -> other: 15; favorite_school -> other: 15; remove -> other: 10; rerank -> other: 10; ask_level -> other: 10.

### Held-out LLM family, raw (as generated)

1361 messages: accuracy 0.5863, macro-F1 0.641.

| type | F1 |
|---|---|
| ask_compare | 0.571 |
| ask_level | 0.583 |
| ask_what_is | 0.5 |
| ask_why_not | 0.671 |
| ask_why_nv | 0.796 |
| change_budget | 0.956 |
| change_near_home | 0.788 |
| change_priority | 0.915 |
| change_score | 0.753 |
| cutoff_shift | 0.125 |
| extra_points | 0.909 |
| favorite_school | 0.613 |
| other | 0.285 |
| own_score | 0.857 |
| remove | 0.575 |
| replace_nganh | 0.657 |
| rerank | 0.876 |
| restore | 0.335 |
| undo | 0.414 |

Most frequent mistakes (true -> predicted): restore -> other: 97; undo -> other: 94; ask_level -> other: 38; ask_why_not -> other: 37; ask_why_nv -> other: 34; favorite_school -> other: 34; remove -> replace_nganh: 28; remove -> other: 21.

## Training data

```
{
  "rows": 12509,
  "unknown_type": 0,
  "empty_or_long": 0,
  "duplicates": 815,
  "review_judgements": {
    "right": 9171,
    "wrong_type": 534,
    "unnatural": 1464,
    "two_requests": 91,
    "unsure": 434,
    "invalid": 0,
    "wrong_type_without_valid_loai_dung": 0,
    "judged_by_people": 0,
    "judged_by_agent": 11694
  },
  "review_rates_by_family": {},
  "agent_review_rates_by_family": {
    "aya": {
      "right": 0.814,
      "wrong_type": 0.089,
      "unnatural": 0.042,
      "unsure": 0.041,
      "two_requests": 0.014,
      "n": 3628
    },
    "gemma": {
      "right": 0.878,
      "unnatural": 0.062,
      "wrong_type": 0.026,
      "unsure": 0.024,
      "two_requests": 0.011,
      "n": 3361
    },
    "mistral": {
      "right": 0.633,
      "unnatural": 0.304,
      "unsure": 0.053,
      "wrong_type": 0.01,
      "n": 1446
    },
    "qwen": {
      "right": 0.734,
      "unnatural": 0.194,
      "unsure": 0.038,
      "wrong_type": 0.033,
      "two_requests": 0.001,
      "n": 3414
    }
  },
  "by_family": {
    "aya": 3270,
    "gemma": 2999,
    "qwen": 2589,
    "mistral": 847
  },
  "relabel_dropped": 57,
  "train": 8801
}
```

## Interim: leave-one-family-out among the training families

Trained on the other training families, tested on the one left out (no relabel filter). Not the main test: that is the held-out family.

### Left out: aya (model)

3270 messages: accuracy 0.882, macro-F1 0.9005.

| type | F1 |
|---|---|
| ask_compare | 0.886 |
| ask_level | 0.963 |
| ask_what_is | 0.9 |
| ask_why_not | 0.842 |
| ask_why_nv | 0.891 |
| change_budget | 0.972 |
| change_near_home | 0.976 |
| change_priority | 0.919 |
| change_score | 0.921 |
| cutoff_shift | 0.836 |
| extra_points | 0.903 |
| favorite_school | 0.913 |
| other | 0.702 |
| own_score | 0.936 |
| remove | 0.854 |
| replace_nganh | 0.947 |
| rerank | 0.977 |
| restore | 0.886 |
| undo | 0.886 |

Most frequent mistakes (true -> predicted): other -> cutoff_shift: 29; ask_why_not -> other: 28; change_score -> other: 27; other -> change_priority: 26; remove -> other: 23; undo -> other: 22; ask_compare -> ask_what_is: 19; other -> extra_points: 18.

### Left out: aya (rule baseline, same messages)

3270 messages: accuracy 0.6813, macro-F1 0.7146.

| type | F1 |
|---|---|
| ask_compare | 0.691 |
| ask_level | 0.954 |
| ask_what_is | 0.604 |
| ask_why_not | 0.672 |
| ask_why_nv | 0.877 |
| change_budget | 0.941 |
| change_near_home | 0.911 |
| change_priority | 0.852 |
| change_score | 0.77 |
| cutoff_shift | 0.491 |
| extra_points | 0.713 |
| favorite_school | 0.66 |
| other | 0.399 |
| own_score | 0.776 |
| remove | 0.62 |
| replace_nganh | 0.769 |
| rerank | 0.841 |
| restore | 0.504 |
| undo | 0.531 |

Most frequent mistakes (true -> predicted): restore -> other: 90; undo -> other: 75; ask_compare -> ask_what_is: 58; remove -> other: 50; other -> ask_what_is: 46; other -> extra_points: 46; ask_why_not -> other: 45; other -> change_score: 42.

### Left out: gemma (model)

2999 messages: accuracy 0.9403, macro-F1 0.9467.

| type | F1 |
|---|---|
| ask_compare | 0.907 |
| ask_level | 0.997 |
| ask_what_is | 0.892 |
| ask_why_not | 0.952 |
| ask_why_nv | 0.968 |
| change_budget | 1.0 |
| change_near_home | 1.0 |
| change_priority | 0.97 |
| change_score | 0.997 |
| cutoff_shift | 0.924 |
| extra_points | 0.954 |
| favorite_school | 0.949 |
| other | 0.775 |
| own_score | 0.911 |
| remove | 0.912 |
| replace_nganh | 0.97 |
| rerank | 1.0 |
| restore | 0.96 |
| undo | 0.948 |

Most frequent mistakes (true -> predicted): ask_what_is -> other: 19; other -> cutoff_shift: 15; own_score -> other: 15; ask_what_is -> ask_compare: 12; undo -> remove: 9; ask_compare -> other: 9; replace_nganh -> remove: 7; ask_why_nv -> other: 7.

### Left out: gemma (rule baseline, same messages)

2999 messages: accuracy 0.6936, macro-F1 0.745.

| type | F1 |
|---|---|
| ask_compare | 0.579 |
| ask_level | 0.787 |
| ask_what_is | 0.602 |
| ask_why_not | 0.646 |
| ask_why_nv | 0.909 |
| change_budget | 0.98 |
| change_near_home | 0.964 |
| change_priority | 0.901 |
| change_score | 0.889 |
| cutoff_shift | 0.684 |
| extra_points | 0.911 |
| favorite_school | 0.757 |
| other | 0.322 |
| own_score | 0.686 |
| remove | 0.685 |
| replace_nganh | 0.834 |
| rerank | 0.854 |
| restore | 0.46 |
| undo | 0.704 |

Most frequent mistakes (true -> predicted): restore -> other: 87; ask_what_is -> other: 79; ask_why_not -> other: 68; own_score -> other: 63; undo -> other: 58; cutoff_shift -> other: 53; remove -> other: 52; ask_compare -> other: 52.

### Left out: qwen (model)

2589 messages: accuracy 0.9255, macro-F1 0.9364.

| type | F1 |
|---|---|
| ask_compare | 0.918 |
| ask_level | 0.975 |
| ask_what_is | 0.926 |
| ask_why_not | 0.965 |
| ask_why_nv | 0.955 |
| change_budget | 0.977 |
| change_near_home | 0.947 |
| change_priority | 0.978 |
| change_score | 0.974 |
| cutoff_shift | 0.93 |
| extra_points | 0.962 |
| favorite_school | 0.922 |
| other | 0.739 |
| own_score | 0.976 |
| remove | 0.879 |
| replace_nganh | 0.901 |
| rerank | 0.934 |
| restore | 0.974 |
| undo | 0.958 |

Most frequent mistakes (true -> predicted): remove -> other: 21; cutoff_shift -> other: 13; ask_what_is -> other: 10; replace_nganh -> remove: 9; replace_nganh -> other: 9; rerank -> other: 8; change_near_home -> other: 7; ask_compare -> ask_what_is: 7.

### Left out: qwen (rule baseline, same messages)

2589 messages: accuracy 0.6605, macro-F1 0.7075.

| type | F1 |
|---|---|
| ask_compare | 0.481 |
| ask_level | 0.866 |
| ask_what_is | 0.735 |
| ask_why_not | 0.626 |
| ask_why_nv | 0.915 |
| change_budget | 0.918 |
| change_near_home | 0.872 |
| change_priority | 0.896 |
| change_score | 0.867 |
| cutoff_shift | 0.65 |
| extra_points | 0.825 |
| favorite_school | 0.708 |
| other | 0.315 |
| own_score | 0.78 |
| remove | 0.613 |
| replace_nganh | 0.78 |
| rerank | 0.619 |
| restore | 0.405 |
| undo | 0.575 |

Most frequent mistakes (true -> predicted): restore -> other: 92; rerank -> other: 65; undo -> other: 61; remove -> other: 57; ask_why_not -> other: 55; cutoff_shift -> other: 45; remove -> replace_nganh: 41; ask_compare -> other: 41.

## Trained model

### Held-out LLM family, after the LLM review (used for the targets)

847 messages: accuracy 0.9693, macro-F1 0.9697.

| type | F1 |
|---|---|
| ask_compare | 0.962 |
| ask_level | 1.0 |
| ask_what_is | 0.889 |
| ask_why_not | 0.965 |
| ask_why_nv | 1.0 |
| change_budget | 1.0 |
| change_near_home | 1.0 |
| change_priority | 1.0 |
| change_score | 1.0 |
| cutoff_shift | 0.933 |
| extra_points | 0.985 |
| favorite_school | 0.957 |
| other | 0.9 |
| remove | 0.957 |
| replace_nganh | 1.0 |
| rerank | 1.0 |
| restore | 0.959 |
| undo | 0.949 |

Most frequent mistakes (true -> predicted): undo -> restore: 3; undo -> remove: 3; ask_why_not -> other: 3; other -> favorite_school: 3; other -> ask_compare: 2; other -> extra_points: 1; restore -> remove: 1; restore -> other: 1.

### Held-out LLM family, raw (as generated)

1361 messages: accuracy 0.8597, macro-F1 0.8808.

| type | F1 |
|---|---|
| ask_compare | 0.938 |
| ask_level | 0.885 |
| ask_what_is | 0.824 |
| ask_why_not | 0.844 |
| ask_why_nv | 0.884 |
| change_budget | 0.991 |
| change_near_home | 0.875 |
| change_priority | 0.99 |
| change_score | 0.988 |
| cutoff_shift | 0.846 |
| extra_points | 0.94 |
| favorite_school | 0.838 |
| other | 0.648 |
| own_score | 0.947 |
| remove | 0.775 |
| replace_nganh | 0.922 |
| rerank | 0.951 |
| restore | 0.868 |
| undo | 0.779 |

Most frequent mistakes (true -> predicted): undo -> other: 19; restore -> other: 13; ask_why_not -> other: 12; extra_points -> other: 11; undo -> remove: 11; ask_level -> other: 10; favorite_school -> other: 10; favorite_school -> remove: 9.

### Check set, all rows

190 messages: accuracy 0.9263, macro-F1 0.9308.

| type | F1 |
|---|---|
| ask_compare | 0.952 |
| ask_level | 1.0 |
| ask_what_is | 0.9 |
| ask_why_not | 0.952 |
| ask_why_nv | 1.0 |
| change_budget | 0.889 |
| change_near_home | 1.0 |
| change_priority | 0.947 |
| change_score | 0.947 |
| cutoff_shift | 0.947 |
| extra_points | 1.0 |
| favorite_school | 0.842 |
| other | 0.643 |
| own_score | 1.0 |
| remove | 0.824 |
| replace_nganh | 1.0 |
| rerank | 1.0 |
| restore | 0.952 |
| undo | 0.889 |

Most frequent mistakes (true -> predicted): change_budget -> other: 2; favorite_school -> other: 2; change_score -> ask_compare: 1; change_priority -> other: 1; remove -> favorite_school: 1; remove -> ask_why_not: 1; remove -> other: 1; undo -> other: 1.

### Check set, rows people judged

190 messages: accuracy 0.9263, macro-F1 0.9308.

| type | F1 |
|---|---|
| ask_compare | 0.952 |
| ask_level | 1.0 |
| ask_what_is | 0.9 |
| ask_why_not | 0.952 |
| ask_why_nv | 1.0 |
| change_budget | 0.889 |
| change_near_home | 1.0 |
| change_priority | 0.947 |
| change_score | 0.947 |
| cutoff_shift | 0.947 |
| extra_points | 1.0 |
| favorite_school | 0.842 |
| other | 0.643 |
| own_score | 1.0 |
| remove | 0.824 |
| replace_nganh | 1.0 |
| rerank | 1.0 |
| restore | 0.952 |
| undo | 0.889 |

Most frequent mistakes (true -> predicted): change_budget -> other: 2; favorite_school -> other: 2; change_score -> ask_compare: 1; change_priority -> other: 1; remove -> favorite_school: 1; remove -> ask_why_not: 1; remove -> other: 1; undo -> other: 1.

Targets reached (and beats the rules): **True**. Saved as `models/message_classifier/model.joblib` (the app loads only `model.joblib`).
