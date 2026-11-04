FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
RUN apt-get update && apt-get install -y --no-install-recommends texlive-latex-extra texlive-fonts-recommended texlive-xetex texlive-luatex fonts-liberation && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home compiler
USER compiler
WORKDIR /work
ENTRYPOINT ["pdflatex", "-no-shell-escape", "-no-parse-first-line", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error"]
