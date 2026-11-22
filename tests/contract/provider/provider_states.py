"""Provider states for the contract between the frontend and the gateway.

The gateway only talks to the microservices through the common layer clients,
so the microservices are replaced by autospecced mocks of the client interfaces.
``create_autospec`` keeps the mocks honest: if the common layer renames a method
or changes its signature, the state setup (and therefore verification) fails.

The contracts between the common layer and the microservices themselves are
verified separately in refractometer-backend.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, create_autospec

from dependency_injector import providers
from refractometer_common.image import Image, ImageClientInterface, ImageNotFoundException
from refractometer_common.queue import (
    QueueClientInterface,
    SimulationQueueElement,
    SimulationQueueElementCreate,
)
from refractometer_common.result import (
    SimulationResult,
    SimulationResultClientInterface,
    SimulationResultNotFoundException,
)
from refractometer_common.sample import (
    CreateSampleRequest,
    Sample,
    SampleClientInterface,
    SampleNotFoundException,
    SellmeierCoefficients,
)
from refractometer_common.spectrum import (
    CreateSpectrumRequest,
    Spectrum,
    SpectrumClientInterface,
    SpectrumNotFoundException,
)

from containers.dependencies import DependencyContainer
from users.user import User

PACT_USER = User(
    id=uuid.UUID(int=1),
    email="pact@example.com",
    name="Pact",
    access=True,
)

IMAGE_ID = "123e4567-e89b-12d3-a456-426614174000"
SAMPLE_ID = "93162ee4-5716-4059-a8a8-fc02e125543f"
SPECTRUM_ID = "4f8c2a1e-6b3d-4e7a-9c5f-2d1b8e3a7c90"
QUEUE_ID = "5a7d3c1b-9e2f-4b6a-8d0c-1f3e5a7b9c2d"
RESULT_ID = "8c2e4a6b-1d3f-4e5a-9b7c-0d2f4a6c8e1b"

ISSUED_AT = datetime(2026, 1, 1, 12, tzinfo=UTC)
PARAMETERS = {"wavelength": 589.3, "sample_id": SAMPLE_ID}


@dataclass
class ClientMocks:
    image: MagicMock
    sample: MagicMock
    spectrum: MagicMock
    queue: MagicMock
    result: MagicMock

    @classmethod
    def create(cls) -> "ClientMocks":
        return cls(
            image=create_autospec(ImageClientInterface, instance=True),
            sample=create_autospec(SampleClientInterface, instance=True),
            spectrum=create_autospec(SpectrumClientInterface, instance=True),
            queue=create_autospec(QueueClientInterface, instance=True),
            result=create_autospec(SimulationResultClientInterface, instance=True),
        )

    def install(self, container: DependencyContainer) -> None:
        for field in fields(self):
            provider = getattr(container, f"{field.name}_client")
            provider.reset_override()
            provider.override(providers.Object(getattr(self, field.name)))


# --- domain fixtures -------------------------------------------------------------------


def _id(params: dict[str, Any], default: str) -> uuid.UUID:
    return uuid.UUID(params.get("id", default))


def make_sample(sample_id: uuid.UUID) -> Sample:
    return Sample(
        id=sample_id,
        name="N-BK7",
        sellmeier_coefficients=SellmeierCoefficients(
            B=[1.03961212, 0.231792344, 1.01046945],
            C=[0.00600069867, 0.0200179144, 103.560653],
        ),
    )


def make_spectrum(spectrum_id: uuid.UUID) -> Spectrum:
    return Spectrum(
        id=spectrum_id,
        name="LED 590nm",
        wavelengths=[400.0, 500.0, 600.0],
        intensities=[0.2, 0.9, 0.4],
    )


def make_queue_element(request: SimulationQueueElementCreate) -> SimulationQueueElement:
    return SimulationQueueElement(
        id=uuid.UUID(QUEUE_ID),
        parameters=request.parameters,
        issued_at=ISSUED_AT,
        name=request.name,
        index=0,
        being_processed=False,
        issuer=request.issuer,
        callback_url=request.callback_url,
    )


def make_result(result_id: uuid.UUID) -> SimulationResult:
    return SimulationResult(
        id=result_id,
        parameters=PARAMETERS,
        image_id=IMAGE_ID,
        issued_at=ISSUED_AT,
        completed_at=ISSUED_AT,
    )


# --- states ----------------------------------------------------------------------------


def image_exists(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.image.get_image.return_value = Image(values=[[0.1, 0.2], [0.3, 0.4]], shape=(2, 2))


def no_image_exists(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.image.get_image.side_effect = ImageNotFoundException("Image not found", 404)


def samples_exist(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.sample.get_all_samples.return_value = [make_sample(uuid.UUID(SAMPLE_ID))]


def sample_exists(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.sample.get_sample.return_value = make_sample(_id(params, SAMPLE_ID))
    mocks.sample.update_sample.side_effect = lambda sample: sample
    mocks.sample.delete_sample.return_value = None


def no_sample_exists(mocks: ClientMocks, params: dict[str, Any]) -> None:
    not_found = SampleNotFoundException("Sample not found", 404)
    for method in ("get_sample", "update_sample", "delete_sample"):
        getattr(mocks.sample, method).side_effect = not_found


def sample_can_be_created(mocks: ClientMocks, params: dict[str, Any]) -> None:
    def create(request: CreateSampleRequest) -> Sample:
        return Sample(
            id=uuid.UUID(SAMPLE_ID),
            name=request.name,
            sellmeier_coefficients=SellmeierCoefficients(B=request.B, C=request.C),
        )

    mocks.sample.create_sample.side_effect = create


def spectrums_exist(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.spectrum.get_all_spectrums.return_value = [make_spectrum(uuid.UUID(SPECTRUM_ID))]


def spectrum_exists(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.spectrum.get_spectrum.return_value = make_spectrum(_id(params, SPECTRUM_ID))
    mocks.spectrum.update_spectrum.side_effect = lambda spectrum: spectrum
    mocks.spectrum.delete_spectrum.return_value = None


def no_spectrum_exists(mocks: ClientMocks, params: dict[str, Any]) -> None:
    not_found = SpectrumNotFoundException("Spectrum not found", 404)
    for method in ("get_spectrum", "update_spectrum", "delete_spectrum"):
        getattr(mocks.spectrum, method).side_effect = not_found


def spectrum_can_be_created(mocks: ClientMocks, params: dict[str, Any]) -> None:
    def create(request: CreateSpectrumRequest) -> Spectrum:
        return Spectrum(id=uuid.UUID(SPECTRUM_ID), **request.model_dump())

    mocks.spectrum.create_spectrum.side_effect = create


def simulations_are_queued(mocks: ClientMocks, params: dict[str, Any]) -> None:
    request = SimulationQueueElementCreate(
        parameters=PARAMETERS, issuer=str(PACT_USER.id), name="pact simulation"
    )
    mocks.queue.get_queued_simulations.return_value = [make_queue_element(request)]


def simulation_can_be_queued(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.queue.create_queued_simulation.side_effect = make_queue_element


def simulation_results_exist(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.result.get_results.return_value = [make_result(uuid.UUID(RESULT_ID))]


def simulation_result_exists(mocks: ClientMocks, params: dict[str, Any]) -> None:
    mocks.result.get_result.return_value = make_result(_id(params, RESULT_ID))
    mocks.result.delete_result.return_value = None


def no_simulation_result_exists(mocks: ClientMocks, params: dict[str, Any]) -> None:
    not_found = SimulationResultNotFoundException("Simulation result not found", 404)
    mocks.result.get_result.side_effect = not_found
    mocks.result.delete_result.side_effect = not_found


STATES: dict[str, Callable[[ClientMocks, dict[str, Any]], None]] = {
    "an image exists": image_exists,
    "no image exists": no_image_exists,
    "samples exist": samples_exist,
    "a sample exists": sample_exists,
    "no sample exists": no_sample_exists,
    "a sample can be created": sample_can_be_created,
    "spectrums exist": spectrums_exist,
    "a spectrum exists": spectrum_exists,
    "no spectrum exists": no_spectrum_exists,
    "a spectrum can be created": spectrum_can_be_created,
    "simulations are queued": simulations_are_queued,
    "a simulation can be queued": simulation_can_be_queued,
    "simulation results exist": simulation_results_exist,
    "a simulation result exists": simulation_result_exists,
    "no simulation result exists": no_simulation_result_exists,
}
