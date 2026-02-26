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

JSON_FILES := \
	build/json/prideaux_1SA.json build/json/web_1SA.json \
	build/json/prideaux_2SA.json build/json/web_2SA.json \
	build/json/prideaux_1KI.json build/json/web_1KI.json

$(JSON_FILES) : $(WEB_USFM_TARGETS) $(PRIDEAUX_USFM_TARGETS) scripts/03_parse_usfm.py
	python3 scripts/03_parse_usfm.py

.PHONY: json
json: $(JSON_FILES)

CSV_TARGETS := \
	build/1_samuel_parallel.csv \
	build/2_samuel_parallel.csv \
	build/1_kings_parallel.csv

$(CSV_TARGETS) : $(JSON_FILES) scripts/05_build_parallel_csv.py
	python3 scripts/05_build_parallel_csv.py

.PHONY: csv
csv: $(CSV_TARGETS)

TEX_TARGETS:= tex/1_samuel_parallel.tex tex/2_samuel_parallel.tex tex/1_kings_parallel.tex

$(TEX_TARGETS) : $(CSV_TARGETS) scripts/06_csv_to_tex.py
	python3 scripts/06_csv_to_tex.py

TEX_SOURCES:= \
	tex/intro.tex \
	tex/preamble.tex \
	tex/title.tex \
	tex/copyright.tex \
	tex/SSD_book.tex

tex/SSD_book.pdf: $(TEX_TARGETS) $(TEX_SOURCES) 
	cd tex && latexmk -xelatex -interaction=nonstopmode -halt-on-error SSD_book.tex

SSD_book.pdf: tex/SSD_book.pdf
	cp tex/SSD_book.pdf .

.PHONY: pdf
pdf: SSD_book.pdf 

.PHONY: clean
clean:
	rm -rf build/*
	rm -f tex/*.aux tex/*.log tex/*.out tex/*.pdf
	rm -f tex/1_samuel_parallel.tex tex/2_samuel_parallel.tex tex/1_kings_parallel.tex
	rm -f tex/SSD_book.fls tex/SSD_book.xdv tex/SSD_book.fdb_latexmk
