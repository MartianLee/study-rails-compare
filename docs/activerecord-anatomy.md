# What Active Record is actually spending

Measured inside the Rails process by `harness/ar_anatomy.py`. 20 rows, a 11-column table, the same four SQL statements at every step.

| step | ms | objects allocated | vs previous |
|---|--:|--:|--:|
| 1. raw mysql2 + hand-built hashes | 0.213 | 602 | - |
| 2. same 4 statements via AR, pluck (no models) | 0.420 | 1,473 | +0.207 ms, +871 objects |
| 3. includes(:user, :tags).to_a (models, attributes untouched) | 0.755 | 3,222 | +0.335 ms, +1,749 objects |
| 4. + full serialisation (every attribute read) | 0.870 | 3,896 | +0.115 ms, +674 objects |

Per row that is **121.2 extra objects** and **22 µs** for the model, on top of running exactly the same SQL.

## What those objects are, for one request

| Ruby type | allocated |
|---|--:|
| `T_OBJECT` | 926 |
| `T_STRING` | 516 |
| `T_HASH` | 766 |
| `T_ARRAY` | 1,227 |
| `T_DATA` | 110 |
| `T_STRUCT` | 13 |
| `T_IMEMO` | 369 |

| class | instances |
|---|--:|
| `ActiveModel::Attribute` | 140 |
| `ActiveModel::AttributeSet` | 137 |
| `ActiveModel::LazyAttributeSet` | 137 |
| `ActiveRecord::Associations::BelongsToAssociation` | 86 |
| `ActiveRecord::Relation` | 66 |
| `Tag` | 31 |
| `Post` | 20 |
| `User` | 20 |
| `ActiveRecord::Result` | 4 |

## Does a wider table cost more per request?

Same 20 rows, same table, same index. Only the number of columns that
become Active Record attributes changes. This is the measured version of
"a god model is slower" — and it says the cost is columns, not model size.

| columns selected | ms | objects | µs per row |
|---|--:|--:|--:|
| 2 | 0.095 | 353 | 5 |
| 4 | 0.104 | 435 | 5 |
| 7 | 0.122 | 438 | 6 |
| 11 | 0.179 | 862 | 9 |

Going from 2 to 11 columns costs **+0.084 ms** and **+509 objects** per request — about **0.5 µs and 2.8 objects per row per column**.
