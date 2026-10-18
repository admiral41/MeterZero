from meterzero import daily, savings


def test_morning_check_flags_the_leak_and_stays_quiet_before_it(small_factory):
    _, _, results = small_factory
    tariff = savings.Tariff()
    leak_morning = results.anomalies["night"].min()
    days = list(results.meter.index.normalize().unique())

    flagged = daily.morning_check(results, leak_morning, tariff)
    assert any(line.kind == "waste" and line.good is False and "compressor" in line.text for line in flagged)

    before = [d for d in days if d < leak_morning]
    for day in before:
        assert not any(line.kind == "waste" for line in daily.morning_check(results, day, tariff))


def test_every_line_is_plain_text_and_the_summary_lists_them(small_factory):
    _, _, results = small_factory
    day = results.meter.index[0].normalize()
    lines = daily.morning_check(results, day, savings.Tariff())
    assert lines and all(isinstance(line.text, str) and line.text.endswith(".") for line in lines)
