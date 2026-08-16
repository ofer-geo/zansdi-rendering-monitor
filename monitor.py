from __future__ import annotations

from datetime import datetime
from pathlib import Path
from database_writer import insert_scale_results
from network import NetworkMonitor
import os
from layers import EXPECTED_LAYERS_BY_SCALE
from dotenv import load_dotenv
from playwright.sync_api import Browser, Page, sync_playwright
import time


MAP_URL = "https://zansdi.org/catalogue/#/map/73"

MONITOR_SEQUENCE = [
    ("1:1,000,000", 0),
    ("1:500,000", 1),
    ("1:250,000", 1),
    ("1:150,000", 1),
    ("1:100,000", 1),
]

WORKER_NUMBER = int(os.getenv("WORKER_NUMBER", "1"))
WORKER_ID = f"User-{WORKER_NUMBER}"

START_DELAY_SECONDS = float(
    os.getenv("START_DELAY_SECONDS", "0")
)

INITIAL_ZOOM_POINTS = [
    (550, 500),
    (590, 710),
    (720, 260),
    (480, 640),
    (510, 550),
    (710, 140),
    (600, 610),
]

CENTER_ZOOM_POINTS = [
    (650, 550),
    (640, 420),
    (640, 420),
    (640, 420),
    (640, 420),
    (640, 420),
    (640, 420),
]

point_index = (
    WORKER_NUMBER - 1
) % len(INITIAL_ZOOM_POINTS)

INITIAL_ZOOM_POINT = INITIAL_ZOOM_POINTS[point_index]
CENTER_ZOOM_POINT = CENTER_ZOOM_POINTS[point_index]

OBSERVATION_SECONDS = 60
SCREENSHOTS_DIRECTORY = Path("artifacts/screenshots")
HEADLESS=True



def safe_scale_name(scale: str) -> str:
    return scale.replace(":", "-").replace(",", "")


def save_screenshot(
    page: Page,
    scenario: str,
    scale: str,
) -> Path:
    SCREENSHOTS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    scale_name = safe_scale_name(scale)
    scenario_name = scenario.replace(" ", "-")

    filename = (
        f"{timestamp}_{WORKER_ID}_{scenario_name}_{scale_name}.jpg"
    )

    path = SCREENSHOTS_DIRECTORY / filename

    page.screenshot(
        path=str(path),
        type="jpeg",
        quality=85,
        full_page=False,
    )

    return path


def save_results(
    page: Page,
    network_monitor: NetworkMonitor,
    cycle_id: str,
    scenario: str,
    scale: str,
) -> None:
    network_monitor.stop_window()

    expected_layers = EXPECTED_LAYERS_BY_SCALE.get(scale, [])

    problem_found = any(
        network_monitor.calculate_status(
            network_monitor.observations[identifier]
        )
        != "Working"
        for identifier in expected_layers
    )

    screenshot_path: Path | None = None

    if problem_found:
        screenshot_path = save_screenshot(
            page=page,
            scenario=scenario,
            scale=scale,
        )

        print(
            f"Problem detected. Screenshot saved: {screenshot_path}",
            flush=True,
        )
    else:
        print(
            "All expected layers are working. No screenshot saved.",
            flush=True,
        )

    network_monitor.print_summary()

    insert_scale_results(
        network_monitor=network_monitor,
        cycle_id=cycle_id,
        worker_id=WORKER_ID,
        scenario=scenario,
        scale=scale,
        screenshot_path=screenshot_path,
    )

def login(page: Page, username: str, password: str) -> None:
    print("Signing in to ZanSDI...", flush=True)

    # Try common GeoNode login links/buttons.
    login_link = page.get_by_text(
        "Sign in",
        exact=False,
    ).first

    if login_link.count() == 0:
        login_link = page.get_by_text(
            "Log in",
            exact=False,
        ).first

    if login_link.count() == 0:
        raise RuntimeError(
            "Could not find the ZanSDI Sign in / Log in control."
        )

    login_link.click()

    page.wait_for_timeout(2_000)

    username_input = page.locator(
        'input[name="login"], '
        'input[name="username"], '
        'input[type="text"]'
    ).first

    password_input = page.locator(
        'input[name="password"], '
        'input[type="password"]'
    ).first

    if username_input.count() == 0:
        raise RuntimeError(
            "Could not find the username input."
        )

    if password_input.count() == 0:
        raise RuntimeError(
            "Could not find the password input."
        )

    username_input.fill(username)
    password_input.fill(password)

    submit_button = page.locator(
        'button[type="submit"], '
        'input[type="submit"]'
    ).first

    if submit_button.count() == 0:
        raise RuntimeError(
            "Could not find the login submit button."
        )

    submit_button.click()

    page.wait_for_timeout(5_000)

    print("Login submitted.", flush=True)

def run_scenario(
    browser: Browser,
    cycle_id: str,
    scenario: str,
    username: str | None = None,
    password: str | None = None,
) -> None:
    print()
    print("#" * 90)
    print(f"Starting scenario: {scenario}")
    print("#" * 90)

    network_monitor = NetworkMonitor()

    # Every call creates a fresh incognito-style context.
    context = browser.new_context(
        viewport={
            "width": 1431,
            "height": 868,
        },
        device_scale_factor=1,
        service_workers="allow",
    )

    page = context.new_page()

    devtools = context.new_cdp_session(page)
    devtools.send("Network.enable")
    devtools.send(
        "Network.setCacheDisabled",
        {
            "cacheDisabled": True,
        },
    )

    context.on(
        "request",
        network_monitor.handle_request,
    )
    context.on(
        "response",
        network_monitor.handle_response,
    )
    context.on(
        "requestfailed",
        network_monitor.handle_request_failed,
    )

    try:
        if scenario == "Signed":
            page.goto(
                MAP_URL,
                wait_until="domcontentloaded",
                timeout=120_000,
            )

            page.wait_for_timeout(5_000)

            if not username or not password:
                raise RuntimeError(
                    "Signed scenario requires username and password."
                )

            login(
                page=page,
                username=username,
                password=password,
            )

            # Open the map again after authentication.
            page.goto(
                MAP_URL,
                wait_until="domcontentloaded",
                timeout=120_000,
            )

            page.wait_for_timeout(3_000)

        print(
            f"Opening ZanSDI web map for {scenario}...",
            flush=True,
        )

        initial_scale, initial_wheel_steps = MONITOR_SEQUENCE[0]

        if initial_wheel_steps != 0:
            raise ValueError(
                "The first MONITOR_SEQUENCE entry must "
                "have 0 wheel steps."
            )

        network_monitor.start_window(initial_scale)

        # Anonymous scenarios have not opened the map yet.
        if scenario != "Signed":
            page.goto(
                MAP_URL,
                wait_until="domcontentloaded",
                timeout=120_000,
            )
        else:
            # Reload to generate a clean initial request set.
            page.reload(
                wait_until="domcontentloaded",
                timeout=120_000,
            )

        print(
            f"Collecting requests for {initial_scale} "
            f"for {OBSERVATION_SECONDS} seconds...",
            flush=True,
        )

        page.wait_for_timeout(
            OBSERVATION_SECONDS * 1000
        )

        save_results(
            page=page,
            network_monitor=network_monitor,
            cycle_id=cycle_id,
            scenario=scenario,
            scale=initial_scale,
        )

        for index, (scale, wheel_steps) in enumerate(
            MONITOR_SEQUENCE[1:]
        ):
            print()
            print("=" * 80)
            print(f"{scenario}: moving automatically to {scale}")
            print("=" * 80)

            if index == 0:
                page.mouse.move(*INITIAL_ZOOM_POINT)
            else:
                page.mouse.move(*CENTER_ZOOM_POINT)

            page.wait_for_timeout(500)

            network_monitor.start_window(scale)

            for _ in range(wheel_steps):
                # Ensure the page and map receive the wheel action.
                page.bring_to_front()
                page.mouse.move(
                    *(INITIAL_ZOOM_POINT if index == 0 else CENTER_ZOOM_POINT)
                )
                page.wait_for_timeout(500)

                page.mouse.wheel(0, -1000)

                # Give the map enough time to finish the zoom animation
                # and issue the new WMS requests.
                page.wait_for_timeout(3_000)

            print(
                f"Collecting requests for {scale} "
                f"for {OBSERVATION_SECONDS} seconds...",
                flush=True,
            )

            page.wait_for_timeout(
                OBSERVATION_SECONDS * 1000
            )

            save_results(
                page=page,
                network_monitor=network_monitor,
                cycle_id=cycle_id,
                scenario=scenario,
                scale=scale,
            )

        print()
        print("=" * 80)
        print(f"{scenario} completed.")
        print("=" * 80)

    finally:
        context.close()

def main() -> None:
    load_dotenv()
    print(
    f"Starting synthetic user: {WORKER_ID}",
        flush=True,
    )

    print(
        f"Start delay: {START_DELAY_SECONDS} seconds",
        flush=True,
    )

    print(
        f"Zoom points: office={INITIAL_ZOOM_POINT}, "
        f"center={CENTER_ZOOM_POINT}",
        flush=True,
    )

    if START_DELAY_SECONDS > 0:
        time.sleep(START_DELAY_SECONDS)

    username = os.getenv(
        f"ZANSDI_USERNAME_{WORKER_NUMBER}"
    )
    password = os.getenv("ZANSDI_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            f"Missing credentials for User-{WORKER_NUMBER}. "
            f"Expected ZANSDI_USERNAME_{WORKER_NUMBER} "
            "and ZANSDI_PASSWORD in the .env file."
        )

    cycle_id = (
        f"{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        f"_{WORKER_ID}"
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=HEADLESS,
        )

        try:
            run_scenario(
                browser=browser,
                cycle_id=cycle_id,
                scenario="Anonymous-1",
            )

            run_scenario(
                browser=browser,
                cycle_id=cycle_id,
                scenario="Signed",
                username=username,
                password=password,
            )

            run_scenario(
                browser=browser,
                cycle_id=cycle_id,
                scenario="Anonymous-2",
            )

        finally:
            browser.close()

    print()
    print("#" * 90)
    print("Complete three-scenario monitoring cycle finished.")
    print(f"Cycle ID: {cycle_id}")
    print("#" * 90)

import subprocess


def run_dbt() -> None:
    project_root = Path(__file__).resolve().parent
    dbt_directory = project_root / "monitoring_dbt"

    print()
    print("#" * 90)
    print("Running dbt transformations and tests...")
    print("#" * 90)

    subprocess.run(
        [
            "dbt",
            "build",
            "--project-dir",
            str(dbt_directory),
            "--profile",
            "monitoring_dbt",
        ],
        cwd=project_root,
        check=True,
    )

    print("dbt completed successfully.", flush=True)


if __name__ == "__main__":
    main()
