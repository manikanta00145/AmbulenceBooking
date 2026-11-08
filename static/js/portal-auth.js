document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-password-toggle]").forEach((toggle) => {
        const password = document.getElementById(toggle.dataset.passwordTarget);
        if (!password) {
            return;
        }

        toggle.addEventListener("click", () => {
            const showPassword = password.type === "password";
            password.type = showPassword ? "text" : "password";
            toggle.setAttribute("aria-label", showPassword ? "Hide password" : "Show password");
            toggle.setAttribute("aria-pressed", String(showPassword));
        });
    });

    const form = document.getElementById("loginForm") || document.getElementById("registrationForm");
    const submit = document.getElementById("submitButton");
    const phone = document.getElementById("id_phone_number");
    const sendOtp = document.getElementById("sendOtpButton");
    const resendOtp = document.getElementById("resendOtpButton");
    const verifyOtp = document.getElementById("verifyOtpButton");
    const otpEntry = document.getElementById("otpEntry");
    const otpCode = document.getElementById("otpCode");
    const countdown = document.getElementById("otpCountdown");
    const otpStatus = document.getElementById("otpStatus");

    const normalizePhone = (value) => value.replace(/\D/g, "");
    const setOtpStatus = (message, success = false) => {
        if (!otpStatus) {
            return;
        }
        otpStatus.textContent = message;
        otpStatus.classList.toggle("success", success);
    };

    const setRegistrationVerified = (isVerified, verifiedPhone = "") => {
        if (!form || form.id !== "registrationForm") {
            return;
        }
        form.dataset.verifiedPhone = isVerified ? verifiedPhone : "";
        if (submit) {
            submit.disabled = !isVerified;
        }
    };

    let countdownInterval;
    const startCountdown = (seconds) => {
        if (!countdown || !resendOtp) {
            return;
        }
        window.clearInterval(countdownInterval);
        let remaining = Math.max(0, Math.ceil(seconds));
        resendOtp.hidden = true;
        countdown.hidden = false;
        const updateCountdown = () => {
            if (remaining <= 0) {
                window.clearInterval(countdownInterval);
                countdown.hidden = true;
                resendOtp.hidden = false;
                return;
            }
            countdown.textContent = `Resend available in ${remaining}s`;
            remaining -= 1;
        };
        updateCountdown();
        countdownInterval = window.setInterval(updateCountdown, 1000);
    };

    const submitOtpRequest = async (url, body) => {
        const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest",
            },
            body: new URLSearchParams({
                csrfmiddlewaretoken: csrfToken,
                phone_number: phone.value,
                ...body,
            }),
        });
        const result = await response.json();
        return { response, result };
    };

    if (form && form.id === "registrationForm" && submit && phone) {
        const verifiedPhone = form.dataset.verifiedPhone || "";
        const alreadyVerified = verifiedPhone
            && normalizePhone(verifiedPhone) === normalizePhone(phone.value);
        setRegistrationVerified(Boolean(alreadyVerified), verifiedPhone);
        if (alreadyVerified) {
            setOtpStatus("Phone number verified.", true);
        }

        phone.addEventListener("input", () => {
            const stillVerified = form.dataset.verifiedPhone
                && normalizePhone(form.dataset.verifiedPhone) === normalizePhone(phone.value);
            if (!stillVerified) {
                setRegistrationVerified(false);
                if (otpCode) {
                    otpCode.value = "";
                }
                setOtpStatus("Verify the new phone number before creating your account.");
            }
        });

        const sendCode = async () => {
            sendOtp.disabled = true;
            resendOtp.disabled = true;
            setOtpStatus("Sending verification code...");
            try {
                const { response, result } = await submitOtpRequest(
                    form.dataset.sendOtpUrl,
                    {},
                );
                if (!response.ok) {
                    setOtpStatus(result.message || "Unable to send a verification code.");
                    if (result.retry_after) {
                        startCountdown(result.retry_after);
                    }
                    return;
                }
                setRegistrationVerified(false);
                otpEntry.hidden = false;
                otpCode.value = "";
                setOtpStatus(result.message);
                startCountdown(result.retry_after);
                otpCode.focus();
            } catch {
                setOtpStatus("Unable to send a verification code. Please try again.");
            } finally {
                sendOtp.disabled = false;
                resendOtp.disabled = false;
            }
        };

        if (sendOtp && resendOtp && otpEntry && otpCode) {
            sendOtp.addEventListener("click", sendCode);
            resendOtp.addEventListener("click", sendCode);
        }

        if (verifyOtp && otpCode) {
            verifyOtp.addEventListener("click", async () => {
                verifyOtp.disabled = true;
                setOtpStatus("Verifying phone number...");
                try {
                    const { response, result } = await submitOtpRequest(
                        form.dataset.verifyOtpUrl,
                        { otp: otpCode.value },
                    );
                    if (!response.ok || !result.verified) {
                        setOtpStatus(result.message || "Unable to verify this code.");
                        return;
                    }
                    setRegistrationVerified(true, phone.value);
                    setOtpStatus(result.message, true);
                } catch {
                    setOtpStatus("Unable to verify this code. Please try again.");
                } finally {
                    verifyOtp.disabled = false;
                }
            });
        }
    }

    if (form && submit) {
        form.addEventListener("submit", () => {
            if (form.id === "registrationForm" && !form.dataset.verifiedPhone) {
                return;
            }
            submit.disabled = true;
            const label = submit.querySelector("span:first-child");
            if (label) {
                label.textContent = form.id === "registrationForm"
                    ? "Creating account..."
                    : "Signing in...";
            }
        });
    }
});
