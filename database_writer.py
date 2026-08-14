from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from layers import EXPECTED_LAYERS_BY_SCALE, LAYERS
from network import LayerObservation, NetworkMonitor


load_dotenv()


def average_response_time(
    observation: LayerObservation,
) -> float | None:
    if not observation.response_times_ms:
        return None

    return round(
        sum(observation.response_times_ms)
        / len(observation.response_times_ms),
        2,
    )


def insert_scale_results(
    network_monitor: NetworkMonitor,
    cycle_id: str,
    worker_id: str,
    scenario: str,
    scale: str,
    screenshot_path: Path | None,
) -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing from the .env file."
        )

    expected_layers = EXPECTED_LAYERS_BY_SCALE.get(scale, [])

    rows = []

    for identifier in expected_layers:
        layer_config = LAYERS[identifier]
        observation = network_monitor.observations[identifier]
        status = network_monitor.calculate_status(observation)

        rows.append(
            (
                cycle_id,
                worker_id,
                scenario,
                scale,
                layer_config["label"],
                identifier,
                layer_config["service"],
                layer_config["request_type"],
                observation.sent,
                observation.successful,
                observation.failed,
                observation.pending,
                average_response_time(observation),
                ", ".join(
                    str(code)
                    for code in observation.status_codes
                ),
                status,
                "; ".join(observation.errors),
                str(screenshot_path) if screenshot_path else None,
            )
        )

    insert_sql = """
        INSERT INTO rendering_observations (
            cycle_id,
            worker_id,
            scenario,
            scale,
            layer_label,
            layer_identifier,
            service,
            request_type,
            requests_sent,
            successful,
            failed,
            pending,
            average_response_ms,
            http_status_codes,
            status,
            notes,
            screenshot_path
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(insert_sql, rows)

        connection.commit()

    print(
        f"Inserted {len(rows)} rows into PostgreSQL.",
        flush=True,
    )