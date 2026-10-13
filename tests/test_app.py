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
