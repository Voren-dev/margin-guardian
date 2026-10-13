"""Step 2: old price list vs new price list -> list of Change.

Plain comparison by supplier code. No model is involved here.

The rule, one Change per thing that changed:
- code only in the new list            -> new_product
- code only in the old list            -> discontinued
- pack size changed                    -> pack_change
- same pack size, listed price changed -> price_up or price_down
- minimum order quantity changed       -> moq_change (on top of the one above, if any)

When the pack size changes, the listed prices of the two lists are not comparable
(a pack of 2 always costs less than a pack of 4). So no price_up or price_down is
emitted for that code: the Change carries both lines, and the analysis step compares
the cost per unit (price / pack_size).

surcharge_note is not produced here: it comes from the notes of the document,
not from comparing two rows.
"""
from mg.schemas import Change, PriceLine


def diff_price_lists(old_lines: list[PriceLine], new_lines: list[PriceLine]) -> list[Change]:
    """Compare two price lists of the same supplier, code by code."""
    old_by_code = _by_code(old_lines)
    new_by_code = _by_code(new_lines)
    changes = []

    # codes of the new list, in the order of the document
    for code, new in new_by_code.items():
        old = old_by_code.get(code)
        if old is None:
            changes.append(Change(supplier_code=code, kind="new_product", new=new))
            continue

        if new.pack_size != old.pack_size:
            changes.append(Change(supplier_code=code, kind="pack_change", old=old, new=new))
        elif _cents(new.price) > _cents(old.price):
            changes.append(Change(supplier_code=code, kind="price_up", old=old, new=new))
        elif _cents(new.price) < _cents(old.price):
            changes.append(Change(supplier_code=code, kind="price_down", old=old, new=new))

        if new.min_order_qty != old.min_order_qty:
            changes.append(Change(supplier_code=code, kind="moq_change", old=old, new=new))

    # codes that disappeared from the new list
    for code, old in old_by_code.items():
        if code not in new_by_code:
            changes.append(Change(supplier_code=code, kind="discontinued", old=old))

    return changes


def _by_code(lines: list[PriceLine]) -> dict[str, PriceLine]:
    """Index the lines by supplier code. The same code twice in one list is an error."""
    by_code = {}
    for line in lines:
        if line.supplier_code in by_code:
            raise ValueError(f"supplier code listed twice: {line.supplier_code}")
        by_code[line.supplier_code] = line
    return by_code


def _cents(price: float) -> int:
    """Prices are compared as whole cents, so 5.1 and 5.10 are the same price."""
    return round(price * 100)
