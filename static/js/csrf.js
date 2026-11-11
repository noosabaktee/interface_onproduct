/*
 * Menambahkan header X-CSRF-Token ke setiap fetch non-GET ke origin yang sama.
 * Token dibaca dari <meta name="csrf-token"> pada base.html dan diverifikasi
 * di server oleh auth_controller.require_login.
 */
(function () {
    "use strict";

    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta ? meta.getAttribute("content") : "";
    if (!token || typeof window.fetch !== "function") {
        return;
    }

    const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
    const nativeFetch = window.fetch.bind(window);

    window.fetch = function (input, init) {
        const isRequest = typeof Request !== "undefined" && input instanceof Request;
        const options = Object.assign({}, init || {});
        const method = String(options.method || (isRequest ? input.method : "GET")).toUpperCase();
        const url = new URL(isRequest ? input.url : String(input), window.location.href);

        if (!SAFE_METHODS.has(method) && url.origin === window.location.origin) {
            const headers = new Headers(options.headers || (isRequest ? input.headers : undefined));
            if (!headers.has("X-CSRF-Token")) {
                headers.set("X-CSRF-Token", token);
            }
            options.headers = headers;
        }
        return nativeFetch(input, options);
    };
})();
