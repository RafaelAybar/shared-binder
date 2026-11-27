FROM php:8.6.0-fpm

COPY --from=composer:latest /usr/bin/composer /usr/bin/composer

RUN groupadd -g 1000 webmaster \
    && useradd -u 1000 -g webmaster -m -s /bin/bash webmaster \
    && mkdir -p /home/webmaster/.composer \
    && chown -R webmaster:webmaster /home/webmaster \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        git \
        libicu-dev \
        libonig-dev \
        libpng-dev \
        libxml2-dev \
        libzip-dev \
        unzip \
        zip \
    && rm -rf /var/lib/apt/lists/*


LABEL authors="rafael"

ENTRYPOINT ["top", "-b"]
