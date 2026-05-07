import csv
import io
import zipfile

import openpyxl
import streamlit as st

from qr_gen import process_csv
from pdf_gen import process_pdf_zip


def _count_records(file) -> int:
    data = file.getvalue()
    if file.name.lower().endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        count = max(0, wb.active.max_row - 1)
        wb.close()
        return count
    return sum(1 for _ in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def _count_zip_files(file) -> int:
    with zipfile.ZipFile(io.BytesIO(file.getvalue())) as zf:
        return sum(1 for n in zf.namelist() if not n.endswith("/"))


st.set_page_config(page_title="Tree QR & PDF Generator", page_icon="🌿", layout="centered")
st.title("Tree QR & PDF Generator")

mode = st.radio("Mode", ["QR Generation", "PDF Generation"], horizontal=True)

if mode == "QR Generation":
    base_url = st.text_input("Base URL *", placeholder="https://example.com")
    upload = st.file_uploader("XLSX or CSV file *", type=["xlsx", "csv"])
    if upload is not None:
        st.caption(f"{_count_records(upload)} Records found.")
    csv_up = None
    zip_up = None
else:
    base_url = ""
    csv_up = st.file_uploader("XLSX or CSV file *", type=["xlsx", "csv"])
    if csv_up is not None:
        st.caption(f"{_count_records(csv_up)} Records found.")
    zip_up = st.file_uploader("Input PDF Zip *", type=["zip"])
    if zip_up is not None:
        st.caption(f"{_count_zip_files(zip_up)} Files found.")
    upload = None

with st.form("main_form"):
    if mode == "QR Generation":
        with st.expander("Help"):
            st.markdown(
                "Required columns: **S\\_No\\_** (tree number) and **Vernacular** (tree name).  \n\n"
                "| S\\_No\\_ | Vernacular |\n"
                "|---------|------------|\n"
                "| 1 | Mangifera indica |\n"
                "| 2 | Ficus benghalensis |\n\n"
                "Each QR code will encode `<Base URL>/<S_No_>.pdf` — e.g. `https://example.com/1.pdf`."
            )
        fmt = st.radio("Output format", ["PNG", "JPG"], horizontal=True)
    else:
        st.caption(
            "Each PDF in the ZIP must be named `<S_No_>.pdf` — e.g. `1.pdf`, `2.pdf`."
        )
        fmt = "PNG"

    label = "Generate QR Codes" if mode == "QR Generation" else "Generate Output PDFs"
    go = st.form_submit_button(label, use_container_width=True, type="primary")

if go:
    errors: list[str] = []
    if mode == "QR Generation":
        if not base_url.strip():
            errors.append("Base URL is required.")
        if upload is None:
            errors.append("Please upload an XLSX or CSV file.")
    else:
        if csv_up is None:
            errors.append("Please upload an XLSX or CSV file.")
        if zip_up is None:
            errors.append("Please upload a ZIP of PDFs.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        with st.spinner("Generating..."):
            bar = st.progress(0, text="Starting...")

            if mode == "QR Generation":
                save_fmt = "JPEG" if fmt == "JPG" else "PNG"
                qr_total = [0]

                def on_qr_progress(done, total):
                    qr_total[0] = total
                    bar.progress(done / total, text=f"Generated {done} of {total} QR codes")

                result, failed_qr = process_csv(upload.getvalue(), base_url.strip(), save_fmt, upload.name, on_progress=on_qr_progress)
                bar.empty()
                n_success = qr_total[0] - len(failed_qr)
                st.success(f"Successfully generated {n_success} QR code{'s' if n_success != 1 else ''}!")
                st.download_button(
                    "Download QR Codes ZIP",
                    data=result,
                    file_name="qr_codes.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
                n_failed = len(failed_qr)
                expander_label = (
                    f"Summary — {n_failed} record(s) could not be processed"
                    if n_failed else "Summary — All records processed successfully"
                )
                with st.expander(expander_label):
                    if failed_qr:
                        st.markdown("The following **S\\_No\\_** records were skipped:")
                        st.markdown("\n".join(f"- {s}" for s in failed_qr))
                    else:
                        st.write("All records were processed successfully.")
            else:
                pdf_total = [0]

                def on_pdf_progress(done, total):
                    pdf_total[0] = total
                    bar.progress(done / total, text=f"Processed {done} of {total} PDFs")

                result, pdf_not_in_xlsx, xlsx_not_in_pdf = process_pdf_zip(zip_up.getvalue(), csv_up.getvalue(), csv_up.name, on_progress=on_pdf_progress)
                bar.empty()
                n_pdfs = pdf_total[0]
                st.success(f"Successfully generated {n_pdfs} PDF{'s' if n_pdfs != 1 else ''}!")
                st.download_button(
                    "Download Modified PDFs ZIP",
                    data=result,
                    file_name="tree_pdfs.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
                n_pdf_only  = len(pdf_not_in_xlsx)
                n_xlsx_only = len(xlsx_not_in_pdf)
                if n_pdf_only > 0 and n_xlsx_only > 0:
                    with st.expander(f"Summary — {n_pdf_only} PDF(s) unmatched, {n_xlsx_only} record(s) unmatched"):
                        st.markdown("**PDFs with no matching record in XLSX:**")
                        st.markdown("\n".join(f"- {name}.pdf" for name in pdf_not_in_xlsx))
                        st.markdown("**XLSX records with no matching PDF:**")
                        st.markdown("\n".join(f"- {s}" for s in xlsx_not_in_pdf))
                elif n_pdf_only > 0:
                    with st.expander(f"Summary — {n_pdf_only} PDF(s) had no matching record"):
                        st.markdown("The following PDFs had **no matching record** in the XLSX:")
                        st.markdown("\n".join(f"- {name}.pdf" for name in pdf_not_in_xlsx))
                elif n_xlsx_only > 0:
                    with st.expander(f"Summary — {n_xlsx_only} record(s) had no matching PDF"):
                        st.markdown("The following **S\\_No\\_** records had no matching PDF in the ZIP:")
                        st.markdown("\n".join(f"- {s}" for s in xlsx_not_in_pdf))
                else:
                    with st.expander("Summary — All records matched"):
                        st.write("All PDFs and records were matched successfully.")
