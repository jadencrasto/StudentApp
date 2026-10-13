/**
 * src/components/attendance/AddSubjectModal.jsx
 * ──────────────────────────────────────────────
 * Form to create a new subject.
 */
import { useState } from "react";
import { Modal, Input, Button } from "../ui/components";
import { attendanceAPI } from "../../api/client";
import toast from "react-hot-toast";

export function AddSubjectModal({ open, onClose, onSuccess }) {
    const [name, setName] = useState("");
    const [code, setCode] = useState("");
    const [loading, setLoading] = useState(false);

    async function handleSubmit(e) {
        e.preventDefault();
        if (!name.trim()) return toast.error("Subject name is required");

        setLoading(true);
        try {
            await attendanceAPI.addSubject({ name, code });
            toast.success("Subject added!");
            setName("");
            setCode("");
            onSuccess();
            onClose();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Failed to add subject");
        } finally {
            setLoading(false);
        }
    }

    return (
        <Modal open={open} onClose={onClose} title="Add New Subject">
            <form onSubmit={handleSubmit} className="space-y-4">
                <Input
                    label="Subject Name"
                    placeholder="e.g. Data Structures"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                />
                <Input
                    label="Subject Code (Optional)"
                    placeholder="e.g. CS301"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                />
                <div className="flex justify-end gap-3 pt-2">
                    <Button type="button" variant="ghost" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button type="submit" loading={loading}>
                        Add Subject
                    </Button>
                </div>
            </form>
        </Modal>
    );
}
