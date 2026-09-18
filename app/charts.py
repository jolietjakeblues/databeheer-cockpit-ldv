def sparkline_points(values: list[float], width: int = 140, height: int = 36, pad: int = 4) -> str:
    """SVG polyline-puntenreeks, genormaliseerd op de eigen min/max van de reeks
    (elke sparkline heeft zijn eigen impliciete schaal - datasets onderling
    vergelijken op absolute grootte is hier niet het doel, alleen de vorm)."""
    if len(values) < 2:
        return ""

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    n = len(values)
    step = (width - 2 * pad) / (n - 1)

    points = []
    for i, v in enumerate(values):
        x = pad + i * step
        y = height - pad - ((v - lo) / span) * (height - 2 * pad)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)
