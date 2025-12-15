"""Tests for the ContainerConfigs helper used by pipelines."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from nf_core.pipelines.containers_utils import ContainerConfigs
from nf_core.utils import NF_INSPECT_MIN_NF_VERSION, pretty_nf_version

from ..test_pipelines import TestPipelines


class TestContainerConfigs(TestPipelines):
    """Tests for ContainerConfigs using a test pipeline."""

    def setUp(self) -> None:
        super().setUp()
        self.container_configs = ContainerConfigs(self.pipeline_dir, "nf-core")

    def test_check_nextflow_version_sufficient_ok(self) -> None:
        """check_nextflow_version should return silently when version is sufficient."""
        with patch(
            "nf_core.pipelines.containers_utils.check_nextflow_version",
            return_value=True,
        ) as mocked_check:
            self.container_configs.check_nextflow_version_sufficient()

        mocked_check.assert_called_once_with(NF_INSPECT_MIN_NF_VERSION)

    def test_check_nextflow_version_sufficient_too_low(self) -> None:
        """check_nextflow_version should raise UserWarning when version is too low."""
        with patch(
            "nf_core.pipelines.containers_utils.check_nextflow_version",
            return_value=False,
        ):
            with pytest.raises(UserWarning) as excinfo:
                self.container_configs.check_nextflow_version_sufficient()

        # Error message should mention the minimal required version
        assert pretty_nf_version(NF_INSPECT_MIN_NF_VERSION) in str(excinfo.value)

    def test_generate_container_configs_mock(self) -> None:
        """Run generate_container_configs with mocking to verify command execution."""
        mock_json_output = b'{"processes": [{"name": "FOO_BAR", "container": "docker://foo/bar:amd64"}]}'

        with patch(
            "nf_core.pipelines.containers_utils.run_cmd",
            return_value=(mock_json_output, b""),
        ) as mocked_run_cmd:
            with patch(
                "nf_core.pipelines.containers_utils.check_nextflow_version",
                return_value=True,
            ):
                # Run and expect warnings about missing meta.yml
                self.container_configs.generate_container_configs()

        expected_cmd_params = f"inspect {self.pipeline_dir} -format json"
        mocked_run_cmd.assert_called_once_with("nextflow", expected_cmd_params)

        # Config files should be created even if meta.yml is missing
        # (they will just be empty except for modules with meta.yml)
        conf_dir = self.pipeline_dir / "conf"
        assert (conf_dir / "containers_docker_amd64.config").exists()

    def test_generate_container_configs_in_pipeline(self) -> None:
        """Run generate_container_configs in a pipeline and verify files are created."""
        # Add container info to FASTQC meta.yml
        fastqc_dir = self.pipeline_dir / "modules" / "nf-core" / "fastqc"
        fastqc_meta_path = fastqc_dir / "meta.yml"

        with fastqc_meta_path.open("r") as fh:
            fastqc_meta = yaml.safe_load(fh)

        fastqc_meta["containers"] = {
            "docker": {
                "linux_amd64": {
                    "name": "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0",
                },
            },
        }

        with fastqc_meta_path.open("w") as fh:
            yaml.safe_dump(fastqc_meta, fh)

        # Run the generation
        self.container_configs.generate_container_configs()

        # Verify config files are created
        conf_path = Path(self.pipeline_dir / "conf" / "containers_docker_amd64.config")
        assert conf_path.exists()
        conf_path_content = conf_path.read_text(encoding="utf-8")

        # FASTQC should be present in the config file since we added meta.yml data
        assert "process { withName: 'FASTQC' { container = 'quay.io/biocontainers/fastqc" in conf_path_content

    def test_generate_container_configs_with_meta(self) -> None:
        """Run generate_container_configs with meta.yml files for all platforms."""
        # TODO: Test with real meta.yml files once they are available in the template
        # Update meta.yml files
        fastqc_dir = self.pipeline_dir / "modules" / "nf-core" / "fastqc"
        meta = {
            "containers": {
                "docker": {
                    "linux_amd64": {
                        "name": "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0",
                    },
                    "linux_arm64": {
                        "name": "community.wave.seqera.io/library/fastqc:0.12.1--d3caca66b4f3d3b0",
                    },
                },
                "singularity": {
                    "linux_amd64": {
                        "name": "oras://community.wave.seqera.io/library/fastqc:0.12.1--0827550dd72a3745",
                        "https": "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/b2/b280a35770a70ed67008c1d6b6db118409bc3adbb3a98edcd55991189e5116f6/data",
                    },
                    "linux_arm64": {
                        "name": "oras://community.wave.seqera.io/library/fastqc:0.12.1--b2ccdee5305e5859",
                        "https": "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/76/76e744b425a6b4c7eb8f12e03fa15daf7054de36557d2f0c4eb53ad952f9b0e3/data",
                    },
                },
                "conda": {
                    "linux_amd64": {
                        "lock_file": "https://wave.seqera.io/v1alpha1/builds/5cfd0f3cb6760c42_1/condalock",
                    },
                    "linux_arm64": {
                        "lock_file": "https://wave.seqera.io/v1alpha1/builds/d3caca66b4f3d3b0_1/condalock",
                    },
                },
            },
        }
        with (fastqc_dir / "meta.yml").open("r") as fh:
            current_meta = yaml.safe_load(fh)
            current_meta.update(meta)
        with (fastqc_dir / "meta.yml").open("w") as fh:
            yaml.safe_dump(current_meta, fh)

        self.container_configs.generate_container_configs()

        conf_dir = self.pipeline_dir / "conf"
        # Expected platforms and one expected container
        expected_platforms = {
            "docker_arm64": {
                "FASTQC": "community.wave.seqera.io/library/fastqc:0.12.1--d3caca66b4f3d3b0",
            },
            "singularity_oras_amd64": {
                "FASTQC": "oras://community.wave.seqera.io/library/fastqc:0.12.1--0827550dd72a3745",
            },
            "singularity_oras_arm64": {
                "FASTQC": "oras://community.wave.seqera.io/library/fastqc:0.12.1--b2ccdee5305e5859",
            },
            "singularity_https_amd64": {
                "FASTQC": "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/b2/b280a35770a70ed67008c1d6b6db118409bc3adbb3a98edcd55991189e5116f6/data",
            },
            "singularity_https_arm64": {
                "FASTQC": "https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/76/76e744b425a6b4c7eb8f12e03fa15daf7054de36557d2f0c4eb53ad952f9b0e3/data",
            },
            "conda_amd64_lockfile": {
                "FASTQC": "https://wave.seqera.io/v1alpha1/builds/5cfd0f3cb6760c42_1/condalock",
            },
            "conda_arm64_lockfile": {
                "FASTQC": "https://wave.seqera.io/v1alpha1/builds/d3caca66b4f3d3b0_1/condalock",
            },
        }

        for platform in expected_platforms.keys():
            cfg_path = conf_dir / f"containers_{platform}.config"
            print(cfg_path)
            assert cfg_path.exists()
            with cfg_path.open("r") as fh:
                content = fh.readlines()
                print(content)
                assert (
                    f"process {{ withName: 'FASTQC' {{ container = '{expected_platforms[platform]['FASTQC']}' }} }}\n"
                    in content
                )
