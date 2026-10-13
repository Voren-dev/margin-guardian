"""Shows a calculation as a table: what is calculated, the formula, the numbers, the result."""
import streamlit as st


def show_trace(calc_trace: str):
    """Each line of a calc_trace is 'what = formula = numbers = result'. Lines without '=' are notes."""
    rows, notes = [], []
    for line in calc_trace.splitlines():
        parts = [part.strip() for part in line.split(" = ")]
        if len(parts) == 1:
            notes.append(line)
        elif len(parts) == 2:
            rows.append({"What": parts[0], "Formula": "", "With the numbers": "", "Result": parts[1]})
        elif len(parts) == 3:
            rows.append({"What": parts[0], "Formula": parts[1], "With the numbers": "", "Result": parts[2]})
        else:
            rows.append({"What": parts[0], "Formula": parts[1], "With the numbers": " = ".join(parts[2:-1]), "Result": parts[-1]})
    st.table(rows)
    for note in notes:
        st.caption(note.capitalize())
