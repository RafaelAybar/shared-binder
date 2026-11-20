FROM php:8.5.11-fpm

COPY --from=composer:latest /usr/bin/composer /usr/bin/composer

RUN groupadd -g 1000 webmaster && \
    useradd -u 1000 -g webmaster -m -s /bin/bash webmaster

RUN mkdir -p /home/webmaster/.composer && \
    chown -R webmaster:webmaster /home/webmaster


RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    libpng-dev \
    libxml2-dev \
    libzip-dev \
    libicu-dev \
    libonig-dev \
    zip \
    unzip \
    && rm -rf /var/lib/apt/lists/*


LABEL authors="rafael"

ENTRYPOINT ["top", "-b"]