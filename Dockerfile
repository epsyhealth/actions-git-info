FROM python:3-slim

RUN pip install poetry --no-cache-dir

WORKDIR /src

RUN apt update && apt install --no-install-recommends -y git && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

COPY . /src

RUN poetry build -f wheel \
  && pip install ./dist/git_info-*-py3-none-any.whl --no-cache-dir

COPY entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
