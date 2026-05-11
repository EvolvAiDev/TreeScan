import csv
import io
import zipfile

import openpyxl
import streamlit as st
import streamlit.components.v2 as components_v2

from qr_gen import process_csv
from pdf_gen import process_pdf_zip

_overlay_renderer = components_v2.component(
    "download_overlay",
    css="""
        #dl-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(255, 255, 255, 0.93);
            z-index: 2147483647;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        #dl-overlay.active { display: flex; }
        .dl-ring {
            width: 52px;
            height: 52px;
            border: 5px solid #ddd;
            border-top-color: #0068c9;
            border-radius: 50%;
            animation: dlspin 0.75s linear infinite;
        }
        @keyframes dlspin { to { transform: rotate(360deg); } }
        .dl-msg {
            margin-top: 18px;
            font: 500 15px/1 sans-serif;
            color: #444;
        }
    """,
    js="""
        export default function ({ el, data }) {
            if (!document.getElementById('dl-overlay')) {
                const ov = document.createElement('div');
                ov.id = 'dl-overlay';
                ov.innerHTML = '<div class="dl-ring"></div><div class="dl-msg">Your download will start shortly…</div>';
                document.body.appendChild(ov);
            }

            clearTimeout(document._dlTimeout);
            const ov = document.getElementById('dl-overlay');
            if (ov) ov.classList.remove('active');

            if (document._dlHandler) document.removeEventListener('click', document._dlHandler, true);
            document._dlHandler = function (e) {
                const btn = e.target.closest('[data-testid="stDownloadButton"] button');
                if (btn && !btn.disabled) {
                    const overlay = document.getElementById('dl-overlay');
                    if (overlay) {
                        overlay.classList.add('active');
                        document._dlTimeout = setTimeout(function () {
                            overlay.classList.remove('active');
                        }, 5000);
                    }
                }
            };
            document.addEventListener('click', document._dlHandler, true);

            return function cleanup() {
                if (document._dlHandler) {
                    document.removeEventListener('click', document._dlHandler, true);
                    document._dlHandler = null;
                }
                clearTimeout(document._dlTimeout);
            };
        }
    """,
    isolate_styles=False,
)


def _download_overlay():
    _overlay_renderer()


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

                result, failed_no_sno, failed_empty_vern, failed_other = process_csv(upload.getvalue(), base_url.strip(), save_fmt, upload.name, on_progress=on_qr_progress)
                bar.empty()
                n_failed  = len(failed_no_sno) + len(failed_empty_vern) + len(failed_other)
                n_success = qr_total[0] - n_failed
                st.session_state["result"] = {
                    "type": "qr",
                    "data": result,
                    "n_success": n_success,
                    "n_failed": n_failed,
                    "failed_no_sno": failed_no_sno,
                    "failed_empty_vern": failed_empty_vern,
                    "failed_other": failed_other,
                }
            else:
                pdf_total = [0]

                def on_pdf_progress(done, total):
                    pdf_total[0] = total
                    bar.progress(done / total, text=f"Processed {done} of {total} PDFs")

                result, pdf_not_in_xlsx, xlsx_not_in_pdf = process_pdf_zip(zip_up.getvalue(), csv_up.getvalue(), csv_up.name, on_progress=on_pdf_progress)
                bar.empty()
                st.session_state["result"] = {
                    "type": "pdf",
                    "data": result,
                    "n_pdfs": pdf_total[0],
                    "pdf_not_in_xlsx": pdf_not_in_xlsx,
                    "xlsx_not_in_pdf": xlsx_not_in_pdf,
                }

res = st.session_state.get("result")
if res:
    _download_overlay()

if res and res["type"] == "qr" and mode == "QR Generation":
    n_success = res["n_success"]
    n_failed  = res["n_failed"]
    st.success(f"Successfully generated {n_success} QR code{'s' if n_success != 1 else ''}!")
    if st.download_button(
        "Download QR Codes ZIP",
        data=res["data"],
        file_name="qr_codes.zip",
        mime="application/zip",
        use_container_width=True,
    ):
        st.toast("Download started!")
    expander_label = (
        f"Summary — {n_failed} record(s) could not be processed"
        if n_failed else "Summary — All records processed successfully"
    )
    with st.expander(expander_label):
        if not n_failed:
            st.write("All records were processed successfully.")
        if res["failed_empty_vern"]:
            st.markdown("**QR not generated because of empty Vernacular column:**")
            st.markdown("\n".join(f"- {s}" for s in res["failed_empty_vern"]))
        if res["failed_no_sno"]:
            st.markdown("**QR not generated because of missing S\\_No\\_:**")
            st.markdown("\n".join(f"- {s}" for s in res["failed_no_sno"]))
        if res["failed_other"]:
            st.markdown("**QR not generated because of unexpected error:**")
            st.markdown("\n".join(f"- {s}" for s in res["failed_other"]))

elif res and res["type"] == "pdf" and mode == "PDF Generation":
    n_pdfs      = res["n_pdfs"]
    n_pdf_only  = len(res["pdf_not_in_xlsx"])
    n_xlsx_only = len(res["xlsx_not_in_pdf"])
    st.success(f"Successfully generated {n_pdfs} PDF{'s' if n_pdfs != 1 else ''}!")
    if st.download_button(
        "Download Modified PDFs ZIP",
        data=res["data"],
        file_name="tree_pdfs.zip",
        mime="application/zip",
        use_container_width=True,
    ):
        st.toast("Download started!")
    if n_pdf_only > 0 and n_xlsx_only > 0:
        with st.expander(f"Summary — {n_pdf_only} PDF(s) unmatched, {n_xlsx_only} record(s) unmatched"):
            st.markdown("**PDFs with no matching record in XLSX:**")
            st.markdown("\n".join(f"- {name}.pdf" for name in res["pdf_not_in_xlsx"]))
            st.markdown("**XLSX records with no matching PDF:**")
            st.markdown("\n".join(f"- {s}" for s in res["xlsx_not_in_pdf"]))
    elif n_pdf_only > 0:
        with st.expander(f"Summary — {n_pdf_only} PDF(s) had no matching record"):
            st.markdown("The following PDFs had **no matching record** in the XLSX:")
            st.markdown("\n".join(f"- {name}.pdf" for name in res["pdf_not_in_xlsx"]))
    elif n_xlsx_only > 0:
        with st.expander(f"Summary — {n_xlsx_only} record(s) had no matching PDF"):
            st.markdown("The following **S\\_No\\_** records had no matching PDF in the ZIP:")
            st.markdown("\n".join(f"- {s}" for s in res["xlsx_not_in_pdf"]))
    else:
        with st.expander("Summary — All records matched"):
            st.write("All PDFs and records were matched successfully.")
