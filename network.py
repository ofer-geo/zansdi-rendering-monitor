from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from urllib.parse import parse_qs, unquote, urlparse


from playwright.sync_api import Request, Response

from layers import LAYERS, EXPECTED_LAYERS_BY_SCALE


@dataclass
class LayerObservation:
    sent: int = 0
    successful: int = 0
    failed: int = 0
    pending: int = 0
    response_times_ms: list[float] = field(default_factory=list)
    status_codes: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class NetworkMonitor:
    def __init__(self) -> None:
        self.enabled = False
        self.current_scale = ""
        self.observations: dict[str, LayerObservation] = {}
        self.active_requests: dict[Request, tuple[str, float]] = {}
        self.reset()

    def reset(self) -> None:
        self.observations = {
            identifier: LayerObservation()
            for identifier in LAYERS
        }
        self.active_requests = {}

    def start_window(self, scale: str) -> None:
        self.reset()
        self.current_scale = scale
        self.enabled = True

        print()
        print("=" * 80)
        print(f"Observation started for scale {scale}")
        print("=" * 80)

    def stop_window(self) -> None:
        self.enabled = False
        self.mark_remaining_as_pending()

    @staticmethod
    def extract_layer_identifier(url: str) -> str | None:
        parsed_url = urlparse(url)

        parameters = {
            key.upper(): values
            for key, values in parse_qs(parsed_url.query).items()
        }

        service = parameters.get("SERVICE", [""])[0].upper()
        request_type = parameters.get("REQUEST", [""])[0].upper()

        if service != "WMS" or request_type != "GETMAP":
            return None

        layer = parameters.get("LAYERS", [""])[0]

        if not layer:
            return None

        return unquote(layer)

    def handle_request(self, request: Request) -> None:
        if not self.enabled:
            return

        layer = self.extract_layer_identifier(request.url)

        if layer is None or layer not in self.observations:
            return

        observation = self.observations[layer]
        observation.sent += 1

        self.active_requests[request] = (
            layer,
            monotonic(),
        )

        print(
            f"SENT: {LAYERS[layer]['label']} | total={observation.sent}",
            flush=True,
        )

    def handle_response(self, response: Response) -> None:
        request = response.request
        active_request = self.active_requests.pop(request, None)

        if active_request is None:
            return

        layer, started_at = active_request
        duration_ms = (monotonic() - started_at) * 1000
        status = response.status

        observation = self.observations[layer]
        observation.response_times_ms.append(duration_ms)
        observation.status_codes.append(status)

        if 200 <= status < 400:
            observation.successful += 1
        else:
            observation.failed += 1
            observation.errors.append(f"HTTP {status}")

        print(
            f"RESPONSE: {LAYERS[layer]['label']} | "
            f"HTTP {status} | {duration_ms:.0f} ms",
            flush=True,
        )

    def handle_request_failed(self, request: Request) -> None:
        active_request = self.active_requests.pop(request, None)

        if active_request is None:
            return

        layer, started_at = active_request
        duration_ms = (monotonic() - started_at) * 1000

        observation = self.observations[layer]
        observation.failed += 1
        observation.response_times_ms.append(duration_ms)

        error_message = request.failure or "Unknown network failure"
        observation.errors.append(error_message)

        print(
            f"FAILED: {LAYERS[layer]['label']} | {error_message}",
            flush=True,
        )

    def mark_remaining_as_pending(self) -> None:
        for request, (layer, _) in list(self.active_requests.items()):
            self.observations[layer].pending += 1
            self.active_requests.pop(request, None)

            print(
                f"PENDING: {LAYERS[layer]['label']}",
                flush=True,
            )

    @staticmethod
    def calculate_status(observation: LayerObservation) -> str:
        if observation.sent == 0:
            return "Request Not Sent"

        if observation.pending > 0:
            if observation.successful > 0 or observation.failed > 0:
                return "Partial Success"
            return "Pending"

        if observation.failed > 0:
            if observation.successful > 0:
                return "Partial Success"
            return "Failed"

        return "Working"

    def print_summary(self) -> None:
        print()
        print("=" * 90)
        print(f"Scale summary: {self.current_scale}")
        print("=" * 90)

        expected_layers = EXPECTED_LAYERS_BY_SCALE.get(
            self.current_scale,
            [],
        )

        for identifier in expected_layers:
            label = LAYERS[identifier]["label"]
            observation = self.observations[identifier]

            if observation.response_times_ms:
                average_response = (
                    sum(observation.response_times_ms)
                    / len(observation.response_times_ms)
                )
                average_text = f"{average_response:.0f} ms"
            else:
                average_text = "-"

            status = self.calculate_status(observation)

            print(f"\n{label}")
            print(f"  Requests sent    : {observation.sent}")
            print(f"  Successful       : {observation.successful}")
            print(f"  Failed           : {observation.failed}")
            print(f"  Pending          : {observation.pending}")
            print(f"  Average response : {average_text}")
            print(f"  HTTP statuses    : {observation.status_codes}")
            print(f"  Status           : {status}")

            if observation.errors:
                print(f"  Errors           : {'; '.join(observation.errors)}")