"""Small runnable policy check: ``python -m vasp_auto.resume``."""
from pathlib import Path
from tempfile import TemporaryDirectory

import json

from . import (
    PREPARERS,
    archive_previous_outputs,
    archive_qe_outputs,
    prepare,
    prepare_qe,
    qe_can_restart_pw,
    qe_remaining_stages,
)


def main() -> None:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        for calc_type in PREPARERS:
            job = root / calc_type
            job.mkdir()
            (job / "POSCAR").write_text("start", encoding="utf-8")
            (job / "INCAR").write_text("IBRION = -1\n", encoding="utf-8")
            if calc_type in {"relax", "vcrelax", "md"}:
                (job / "CONTCAR").write_text("continued", encoding="utf-8")
            if calc_type in {"dos", "bands"}:
                (job / "CHGCAR").write_text("checkpoint", encoding="utf-8")
            images = []
            if calc_type in {"neb", "tss"}:
                image = job / "01"
                image.mkdir()
                (image / "POSCAR").write_text("image start", encoding="utf-8")
                (image / "CONTCAR").write_text("image continued", encoding="utf-8")
                images = [image]
            prepare(calc_type, job, images)

        freq = root / "freq"
        (freq / "INCAR").write_text("IBRION = 6\n", encoding="utf-8")
        (freq / "vaspcheckfd.h5").write_text("checkpoint", encoding="utf-8")
        prepare("freq", freq)
        assert "CHECKPOINT_FD = CONTINUE" in (freq / "INCAR").read_text()

        scf = root / "scf"
        (scf / "OUTCAR").write_text("partial", encoding="utf-8")
        archive = archive_previous_outputs(scf, [], "scf")
        assert archive and (archive / "OUTCAR").read_text() == "partial"
        assert not (scf / "OUTCAR").exists()

        qe = root / "qe"
        qe.mkdir()
        (qe / "pw.in").write_text(
            "&CONTROL\n calculation = 'relax'\n prefix = 'test'\n outdir = './tmp'\n/\n",
            encoding="utf-8",
        )
        save = qe / "tmp" / "test.save"
        save.mkdir(parents=True)
        (save / "data-file-schema.xml").write_text("checkpoint", encoding="utf-8")
        stages = [{"program": "pw.x", "input": "pw.in", "output": "pw.out", "mpi": True}]
        (qe / "qe_stages.json").write_text(json.dumps({"calc_type": "relax", "stages": stages}))
        (qe / "pw.out").write_text("Maximum CPU time exceeded\n", encoding="utf-8")
        remaining = qe_remaining_stages(qe)
        assert qe_can_restart_pw(qe, remaining[0])
        archive_qe_outputs(qe, remaining, "relax")
        prepare_qe("relax", qe, remaining[0])
        assert "restart_mode = 'restart'" in (qe / "pw.in").read_text()
        assert "Maximum CPU time exceeded" in (qe / "resume_history" / "0001" / "pw.out").read_text()
    print("resume policies: OK")


if __name__ == "__main__":
    main()
