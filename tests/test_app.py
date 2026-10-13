from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def _app():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_app_waits_for_a_file():
    app = _app()
    assert not app.exception
    assert app.info
    assert "sample" in app.info[0].value.lower()
    assert app.selectbox[0].value == "CSV"
    assert app.selectbox[1].value == "None"


def test_sample_csv_and_xml_preview_real_rows():
    app = _app()
    app.selectbox[1].set_value("CSV")
    app.run()
    assert not app.exception
    preview = app.dataframe[0].value
    assert preview["name"].tolist() == ["Alice", "Bob", "Carol"]
    assert app.download_button[0].label == "Download sample.csv"

    app.selectbox[1].set_value("XML")
    app.run()
    assert not app.exception
    xml_preview = app.dataframe[0].value
    assert xml_preview["name"].tolist() == ["Alice", "Bob"]


def test_upload_without_an_extension_is_explained():
    app = _app()
    app.file_uploader[0].set_value(("notes", b"hello", "application/octet-stream"))
    app.run()
    message = " ".join(str(item.value) for item in [*app.exception, *app.error])
    assert "extension" in message.lower()


def test_corrupt_upload_is_explained():
    app = _app()
    app.file_uploader[0].set_value(("broken.pdf", b"not a pdf", "application/pdf"))
    app.run()
    assert any("PDF" in error.value for error in app.error)


def test_word_sample_previews_as_pdf_document():
    app = _app()
    app.selectbox[0].set_value("PDF (.pdf)")
    app.selectbox[1].set_value("Word")
    app.run()
    assert not app.exception
    assert app.text_area
    assert app.download_button[0].label == "Download sample.pdf"


def test_every_sample_converts_to_every_format():
    from converter import SUPPORTED_OUTPUTS

    app = _app()
    for sample in ["CSV", "JSON", "XML", "Markdown", "Word", "PDF"]:
        for output in SUPPORTED_OUTPUTS:
            app.selectbox[0].set_value(output)
            app.selectbox[1].set_value(sample)
            app.run()
            assert not app.exception, (sample, output)
            assert not app.error, (sample, output, [e.value for e in app.error])
            assert app.download_button

