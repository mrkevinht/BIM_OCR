const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const fileInput = document.getElementById("fileInput");
const uploadStatus = document.getElementById("uploadStatus");
const workerBadge = document.getElementById("workerBadge");
const jobsBody = document.getElementById("jobsBody");
const jobCount = document.getElementById("jobCount");

const DEFAULT_TASKS = ["layout", "rooms", "annotations"];

function addMessage(role, text) {
    const bubble = document.createElement("div");
    bubble.className = `chat-message ${role}`;
    bubble.textContent = text;
    chatLog.appendChild(bubble);
    chatLog.scrollTop = chatLog.scrollHeight;
}

function addDockerMessage(text) {
    addMessage("bot", text);
}

function addUserMessage(text) {
    addMessage("user", text);
}

async function checkHealth() {
    try {
        const response = await fetch("/healthz");
        if (response.ok) {
            setWorkerBadge(true);
            return;
        }
        setWorkerBadge(false);
    } catch (error) {
        setWorkerBadge(false);
    }
}

function setWorkerBadge(isOnline) {
    workerBadge.textContent = isOnline ? "Online" : "Offline";
    workerBadge.classList.toggle("online", isOnline);
    workerBadge.classList.toggle("offline", !isOnline);
}

async function fetchJobs({ silent = false } = {}) {
    try {
        const response = await fetch("/api/v1/documents");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const jobs = await response.json();
        renderJobs(jobs);
        if (!silent) {
            respondWithJobs(jobs);
        }
        return jobs;
    } catch (error) {
        renderJobs([]);
        if (!silent) {
            addDockerMessage("Không thể tải danh sách job. Hãy thử lại sau.");
        }
        return [];
    }
}

function renderJobs(jobs) {
    jobsBody.innerHTML = "";
    jobCount.textContent = jobs.length.toString();

    if (!jobs.length) {
        const row = document.createElement("tr");
        row.className = "empty-row";
        row.innerHTML = '<td colspan="3">Chưa có job nào.</td>';
        jobsBody.appendChild(row);
        return;
    }

    jobs.forEach((job) => {
        const row = document.createElement("tr");

        const idCell = document.createElement("td");
        idCell.textContent = job.id.slice(0, 8);

        const fileCell = document.createElement("td");
        fileCell.textContent = job.filename;

        const statusCell = document.createElement("td");
        statusCell.textContent = job.status;

        row.appendChild(idCell);
        row.appendChild(fileCell);
        row.appendChild(statusCell);
        jobsBody.appendChild(row);
    });
}

function respondWithJobs(jobs) {
    if (!jobs.length) {
        addDockerMessage("Chưa có job nào trong hệ thống. Hãy tải lên một bản vẽ để bắt đầu.");
        return;
    }

    const summary = jobs
        .slice(0, 3)
        .map((job) => `${job.filename} → ${job.status}`)
        .join("\n");

    let footer = "";
    if (jobs.length > 3) {
        footer = `\n(+${jobs.length - 3} job khác)`;
    }

    addDockerMessage(`Đã tìm thấy ${jobs.length} job:\n${summary}${footer}`);
}

async function handleUpload(file) {
    uploadStatus.textContent = `Đang tải lên ${file.name}…`;
    addUserMessage(`Tôi vừa tải lên tệp: ${file.name}`);
    const params = new URLSearchParams();
    DEFAULT_TASKS.forEach((task) => params.append("tasks", task));

    const body = new FormData();
    body.append("file", file, file.name);

    try {
        const response = await fetch(`/api/v1/documents?${params.toString()}`, {
            method: "POST",
            body,
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || `Upload failed with ${response.status}`);
        }

        const job = await response.json();
        uploadStatus.textContent = `Đã gửi job ${job.id.slice(0, 8)}. Worker đang xử lý…`;
        addDockerMessage(
            `Đã nhận tệp ${job.filename}. Job ${job.id.slice(0, 8)} đang ở trạng thái ${job.status}.`
        );
        fetchJobs({ silent: true });
    } catch (error) {
        uploadStatus.textContent = "Tải lên thất bại. Vui lòng thử lại.";
        addDockerMessage(
            `Không thể tải lên tệp. Lỗi: ${error.message || "không xác định"}`
        );
    } finally {
        fileInput.value = "";
    }
}

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = chatInput.value.trim();
    if (!text) {
        return;
    }

    addUserMessage(text);
    chatInput.value = "";

    const lower = text.toLowerCase();

    if (lower.includes("status") || lower.includes("trạng thái") || lower.includes("progress")) {
        await fetchJobs();
        return;
    }

    if (lower.includes("health") || lower.includes("worker")) {
        await checkHealth();
        const badgeText = workerBadge.textContent;
        addDockerMessage(`Worker hiện đang: ${badgeText}.`);
        return;
    }

    if (lower.includes("help") || lower.includes("hướng dẫn")) {
        addDockerMessage(
            "Bạn có thể tải lên bản vẽ bằng nút bên phải. Gõ \"status\" để xem tiến độ hoặc \"worker\" để kiểm tra kết nối."
        );
        return;
    }

    addDockerMessage("Docker sẵn sàng hỗ trợ. Hãy yêu cầu \"status\" hoặc tải lên một bản vẽ.");
});

fileInput.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) {
        return;
    }
    const allowed = [".pdf", ".png", ".jpg", ".jpeg", ".webp"];
    const lowerName = file.name.toLowerCase();
    const isAllowed = allowed.some((ext) => lowerName.endsWith(ext));
    if (!isAllowed) {
        uploadStatus.textContent = "Vui lòng chọn PDF hoặc hình ảnh (png, jpg, webp).";
        fileInput.value = "";
        addDockerMessage("Định dạng tệp không được hỗ trợ.");
        return;
    }
    handleUpload(file);
});

addDockerMessage("Xin chào! Tôi là Docker. Hãy tải lên bản vẽ hoặc hỏi tôi về trạng thái xử lý.");

checkHealth();
fetchJobs({ silent: true });

setInterval(checkHealth, 15000);
setInterval(() => fetchJobs({ silent: true }), 12000);
