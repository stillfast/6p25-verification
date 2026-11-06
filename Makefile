# Convenience wrapper around the folder READMEs.
#
#   make structures    import the shipped ACWF structure archive (once)
#   make pseudos       upload the two pseudopotentials and build the family
#   make subgroups     create the per-configuration structure subgroups
#   make verify        check that the family / code / groups are ready
#   make convergence   cutoff scan (add RUN=1 to actually submit)
#   make cutoffs       pick the converged cutoffs into 2-convergence/cutoffs.json
#   make submit        production EOS campaign (add RUN=1 to actually submit)
#   make analyze       results, audit, metrics, comparison, plots, provenance CSV
#
# Every target runs in the current conda env; see README for setup.

PYTHON ?= python
PSEUDOS ?= 6p25
RUN ?=
RUNFLAG := $(if $(RUN),--run,)

.PHONY: help structures pseudos subgroups verify convergence cutoffs submit analyze all

help:
	@grep -E '^#   ' Makefile

structures:
	$(PYTHON) 1-preliminary/import_structures.py

pseudos:
	$(PYTHON) 1-preliminary/install_pseudos.py

subgroups:
	$(PYTHON) 1-preliminary/create_starting_subgroups.py

verify:
	$(PYTHON) 1-preliminary/verify_setup.py

convergence:
	$(PYTHON) 2-convergence/run_cutoff_convergence.py --pseudos $(PSEUDOS) \
		--cutoffs 110 150 200 250 --max-memory-gb 100 $(RUNFLAG)

cutoffs:
	$(PYTHON) 2-convergence/select_cutoffs.py --pseudos $(PSEUDOS)

submit:
	$(PYTHON) 3-submit/launch_calculations_qe.py --pseudos $(PSEUDOS) \
		--max-memory-gb 100 $(RUNFLAG)

analyze:
	bash 4-analyze/run_analysis.sh $(PSEUDOS)

all: structures pseudos subgroups verify convergence cutoffs submit analyze
