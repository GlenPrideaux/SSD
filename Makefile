all: pdf

build/md/SSD.md : sources/odt/sk_all_2ed.odt
	mkdir -p build/md/
	pandoc sources/odt/sk_all_2ed.odt -t markdown -o build/md/SSD.md 

MD_SPLITS := build/md/Prideaux-1SA.md build/md/Prideaux-2SA.md build/md/Prideaux-1KI.md

$(MD_SPLITS) : build/md/SSD.md scripts/00_split_ssd_md.py
	python3 scripts/00_split_ssd_md.py build/md/SSD.md --outdir build/md
	sed -i '' '1s/^\[\^52\][[:space:]]*//' build/md/Prideaux-1KI.md

build/temp/Prideaux-%.temp : build/md/Prideaux-%.md scripts/01_convert_verses.py
	mkdir -p build/temp
	python3 scripts/01_convert_verses.py $< $@ --id $*

build/usfm/prideaux/Prideaux-%.usfm : build/temp/Prideaux-%.temp build/md/SSD.md scripts/02_convert_footnotes.py
	mkdir -p build/usfm/prideaux
	python3 scripts/02_convert_footnotes.py build/md/SSD.md $< $@

PRIDEAUX_USFM_TARGETS := \
	build/usfm/prideaux/Prideaux-1SA.usfm \
	build/usfm/prideaux/Prideaux-2SA.usfm \
	build/usfm/prideaux/Prideaux-1KI.usfm

WEB_USFM_ZIP := sources/eng-web_usfm.zip
WEB_USFM_TMP := build/eng-web_usfm_extract

WEB_USFM_TARGETS := \
	build/usfm/web/10-1SAeng-web.usfm \
	build/usfm/web/11-2SAeng-web.usfm \
	build/usfm/web/12-1KIeng-web.usfm

$(WEB_USFM_ZIP):
	mkdir -p build
	curl -L -o $@ https://ebible.org/Scriptures/eng-web_usfm.zip

$(WEB_USFM_TARGETS): $(WEB_USFM_ZIP)
	mkdir -p build/usfm/web
	rm -rf $(WEB_USFM_TMP)
	mkdir -p $(WEB_USFM_TMP)
	unzip -q $(WEB_USFM_ZIP) -d $(WEB_USFM_TMP)
	cp $(WEB_USFM_TMP)/10-1SAeng-web.usfm build/usfm/web/
	cp $(WEB_USFM_TMP)/11-2SAeng-web.usfm build/usfm/web/
	cp $(WEB_USFM_TMP)/12-1KIeng-web.usfm build/usfm/web/
	rm -rf $(WEB_USFM_TMP)

.PHONY: fetch-web-usfm
fetch-web-usfm: $(WEB_USFM_TARGETS)

WEBBE_USFM_ZIP := sources/eng-webbe_usfm.zip
WEBBE_USFM_TMP := build/eng-webbe_usfm_extract

WEBBE_USFM_TARGETS := \
	build/usfm/webbe/10-1SAeng-webbe.usfm \
	build/usfm/webbe/11-2SAeng-webbe.usfm \
	build/usfm/webbe/12-1KIeng-webbe.usfm

$(WEBBE_USFM_ZIP):
	mkdir -p build
	curl -L -o $@ https://ebible.org/Scriptures/eng-webbe_usfm.zip

$(WEBBE_USFM_TARGETS): $(WEBBE_USFM_ZIP)
	mkdir -p build/usfm/webbe
	rm -rf $(WEBBE_USFM_TMP)
	mkdir -p $(WEBBE_USFM_TMP)
	unzip -q $(WEBBE_USFM_ZIP) -d $(WEBBE_USFM_TMP)
	cp $(WEBBE_USFM_TMP)/10-1SAeng-webbe.usfm build/usfm/webbe/
	cp $(WEBBE_USFM_TMP)/11-2SAeng-webbe.usfm build/usfm/webbe/
	cp $(WEBBE_USFM_TMP)/12-1KIeng-webbe.usfm build/usfm/webbe/
	rm -rf $(WEB_USFM_TMP)

.PHONY: fetch-webbe-usfm
fetch-webbe-usfm: $(WEBBE_USFM_TARGETS)

JSON_FILES := \
	build/json/prideaux_1SA.json build/json/web_1SA.json build/json/webbe_1SA.json \
	build/json/prideaux_2SA.json build/json/web_2SA.json build/json/webbe_2SA.json \
	build/json/prideaux_1KI.json build/json/web_1KI.json build/json/webbe_1KI.json

$(JSON_FILES) : $(WEB_USFM_TARGETS) $(WEBBE_USFM_TARGETS) $(PRIDEAUX_USFM_TARGETS) scripts/03_parse_usfm.py
	python3 scripts/03_parse_usfm.py

.PHONY: json
json: $(JSON_FILES)

CSV_PAR_TARGETS := \
	build/1_samuel_parallel.csv \
	build/2_samuel_parallel.csv \
	build/1_kings_parallel.csv

$(CSV_PAR_TARGETS) : $(JSON_FILES) scripts/05_build_parallel_csv.py
	python3 scripts/05_build_parallel_csv.py

CSV_PAR_BE_TARGETS := \
	build/1_samuel_parallel_be.csv \
	build/2_samuel_parallel_be.csv \
	build/1_kings_parallel_be.csv

$(CSV_PAR_BE_TARGETS) : $(JSON_FILES) scripts/05_build_parallel_csv.py
	python3 scripts/05_build_parallel_csv.py -b

CSV_TARGETS := \
	build/1_samuel.csv \
	build/2_samuel.csv \
	build/1_kings.csv

$(CSV_TARGETS) : $(JSON_FILES) scripts/05_build_csv.py
	python3 scripts/05_build_csv.py

.PHONY: csv
csv: $(CSV_PAR_TARGETS) $(CSV_PAR_BE_TARGETS) $(CSV_TARGETS)

TEX_PAR_TARGETS:= tex/1_samuel_parallel.tex tex/2_samuel_parallel.tex tex/1_kings_parallel.tex

$(TEX_PAR_TARGETS) : $(CSV_PAR_TARGETS) scripts/06_csv_to_parallel_tex.py
	python3 scripts/06_csv_to_parallel_tex.py

TEX_PAR_BE_TARGETS:= tex/1_samuel_parallel_be.tex tex/2_samuel_parallel_be.tex tex/1_kings_parallel_be.tex

$(TEX_PAR_BE_TARGETS) : $(CSV_PAR_BE_TARGETS) scripts/06_csv_to_parallel_tex.py
	python3 scripts/06_csv_to_parallel_tex.py -b

TEX_TARGETS:= tex/1_samuel.tex tex/2_samuel.tex tex/1_kings.tex

$(TEX_TARGETS) : $(CSV_TARGETS) scripts/06_csv_to_tex.py
	python3 scripts/06_csv_to_tex.py

tex/concordance.tex : scripts/07_make_concordance.py $(CSV_TARGETS) data/stoplist.csv data/force_lower.csv
	python3 scripts/07_make_concordance.py

.PHONY: tex
tex: $(TEX_PAR_TARGETS) $(TEX_PAR_BE_TARGETS) $(TEX_TARGETS)

TEX_PAR_SOURCES:= \
	tex/intro_parallel.tex \
	tex/preamble_parallel.tex \
	tex/title_parallel.tex \
	tex/copyright_parallel.tex \
	tex/SSD_parallel_book.tex

TEX_PAR_BE_SOURCES:= \
	tex/intro_parallel_be.tex \
	tex/preamble_parallel.tex \
	tex/title_parallel_be.tex \
	tex/copyright_parallel_be.tex \
	tex/SSD_parallel_be_book.tex

TEX_SOURCES:= \
	tex/intro.tex \
	tex/preamble.tex \
	tex/title.tex \
	tex/copyright.tex \
	tex/concordance.tex \
	tex/SSD_book.tex

tex/SSD_parallel_book.pdf: $(TEX_PAR_TARGETS) $(TEX_PAR_SOURCES) 
	cd tex && latexmk -xelatex -interaction=nonstopmode -halt-on-error SSD_parallel_book.tex

tex/SSD_parallel_be_book.pdf: $(TEX_PAR_BE_TARGETS) $(TEX_PAR_BE_SOURCES) 
	cd tex && latexmk -xelatex -interaction=nonstopmode -halt-on-error SSD_parallel_be_book.tex

tex/SSD_book.pdf: $(TEX_TARGETS) $(TEX_SOURCES) 
	cd tex && latexmk -xelatex -interaction=nonstopmode -halt-on-error SSD_book.tex

SSD_parallel_book.pdf: tex/SSD_parallel_book.pdf
	cp tex/SSD_parallel_book.pdf .

SSD_parallel_be_book.pdf: tex/SSD_parallel_be_book.pdf
	cp tex/SSD_parallel_be_book.pdf .

SSD_book.pdf: tex/SSD_book.pdf
	cp tex/SSD_book.pdf .

.PHONY: pdf
pdf: SSD_parallel_book.pdf SSD_parallel_be_book.pdf SSD_book.pdf

.PHONY: clean
clean:
	rm -rf build/*
	rm -f tex/*.aux tex/*.log tex/*.out tex/*.pdf
	rm -f tex/1_samuel*.tex tex/2_samuel*.tex tex/1_kings*.tex tex/concordance.tex
	rm -f tex/SSD*_book.fls tex/SSD*_book.xdv tex/SSD*_book.fdb_latexmk
