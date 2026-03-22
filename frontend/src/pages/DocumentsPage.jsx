/**
 * src/pages/DocumentsPage.jsx
 * ────────────────────────────
 * Upload PDF/image/text → backend extracts assignments → list documents.
 */
import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Upload, FileText, Image, File, CheckCircle, XCircle, Clock, RefreshCw } from "lucide-react";
import toast from "react-hot-toast";
import { documentsAPI } from "../lib/api";
import {
  Card, Badge, Button, Spinner, EmptyState, PageHeader,
} from "../components/ui/components";

const STATUS_ICON = {
  pending:    <Clock size={14} className="text-slate-400" />,
  processing: <RefreshCw size={14} className="text-info animate-spin" />,
  done:       <CheckCircle size={14} className="text-ok" />,
  failed:     <XCircle size={14} className="text-danger" />,
};
const STATUS_BADGE = {
  pending: "default", processing: "info", done: "success", failed: "danger"
};
const FILE_ICON = {
  pdf:   <FileText size={20} className="text-red-400" />,
  image: <Image size={20} className="text-blue-400" />,
  txt:   <File size={20} className="text-slate-400" />,
};

function DropZone({ onFile }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef();

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) onFile(file);
  };

  return (
    <div
      className={`relative border-2 border-dashed rounded-2xl p-12 text-center transition-all cursor-pointer ${
        dragging
          ? "border-emerald-500 bg-emerald-500/5"
          : "border-white/10 hover:border-emerald-500/30 bg-black/40 backdrop-blur-md"
      }`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.txt"
        onChange={(e) => e.target.files[0] && onFile(e.target.files[0])}
      />
      <div className="flex flex-col items-center gap-3">
        <div className="w-14 h-14 bg-white/5 border border-white/10 rounded-2xl flex items-center justify-center">
          <Upload size={24} className="text-emerald-500" />
        </div>
        <div>
          <p className="text-paper font-medium">Drop a file here or click to browse</p>
          <p className="text-slate-500 text-sm mt-1">PDF, PNG, JPEG, or TXT — max 10 MB</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="px-2 py-1 bg-white/5 border border-white/10 rounded">PDF</span>
          <span className="px-2 py-1 bg-white/5 border border-white/10 rounded">DOC</span>
          <span className="px-2 py-1 bg-white/5 border border-white/10 rounded">DOCX</span>
          <span className="px-2 py-1 bg-white/5 border border-white/10 rounded">PNG</span>
          <span className="px-2 py-1 bg-white/5 border border-white/10 rounded">JPEG</span>
          <span className="px-2 py-1 bg-white/5 border border-white/10 rounded">TXT</span>
        </div>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const selectedDocId = searchParams.get("doc");

  const { data: documents = [], isLoading, refetch } = useQuery({
    queryKey: ["documents"],
    queryFn: () => documentsAPI.list().then((r) => r.data),
    refetchInterval: (data) => {
      // Poll every 3s if any doc is still processing
      const processing = data?.some(
        (d) => d.extraction_status === "processing" || d.extraction_status === "pending"
      );
      return processing ? 3000 : false;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (file) => documentsAPI.upload(file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["assignments"] });
      toast.success("File uploaded — extracting content...");
    },
    onError: (err) => {
      const msg = err.response?.data?.detail || "Upload failed";
      toast.error(msg);
    },
  });

  useEffect(() => {
    if (!selectedDocId || !documents.length) return;
    const target = document.getElementById(`document-${selectedDocId}`);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [selectedDocId, documents]);

  return (
    <div>
      <PageHeader
        title="Documents"
        subtitle="Upload PDFs or images — AI extracts assignments automatically"
        action={
          <Button variant="ghost" onClick={() => refetch()}>
            <RefreshCw size={14} /> Refresh
          </Button>
        }
      />

      {/* Drop Zone */}
      <DropZone onFile={(file) => uploadMutation.mutate(file)} />

      {uploadMutation.isPending && (
        <div className="flex items-center justify-center gap-2 mt-4 text-info text-sm">
          <Spinner size={16} /> Uploading and processing...
        </div>
      )}

      {/* Document List */}
      <div className="mt-8">
        <h2 className="text-paper font-display font-semibold text-lg mb-4">Uploaded Files</h2>

        {isLoading ? (
          <div className="flex justify-center py-12"><Spinner size={28} /></div>
        ) : documents.length === 0 ? (
          <Card>
            <EmptyState
              icon={FileText}
              message="No documents uploaded yet. Drop a file above to get started."
            />
          </Card>
        ) : (
          <div className="space-y-3">
            {documents.map((doc) => (
              <Card
                id={`document-${doc.id}`}
                key={doc.id}
                className={`hover:border-emerald-500/30 transition-colors ${selectedDocId === doc.id ? "ring-2 ring-emerald-500/40 border-emerald-500/40" : ""}`}
              >
                <div className="flex items-center gap-4">
                  {/* File type icon */}
                  <div className="w-10 h-10 bg-white/5 border border-white/10 rounded-xl flex items-center justify-center flex-shrink-0">
                    {FILE_ICON[doc.file_type] || FILE_ICON.txt}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-paper font-medium text-sm truncate">{doc.filename}</p>
                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                      <span>{doc.file_size_kb} KB</span>
                      <span>{format(new Date(doc.created_at), "d MMM yyyy, HH:mm")}</span>
                    </div>
                  </div>

                  {/* Extraction status */}
                  <div className="flex items-center gap-3 flex-shrink-0">
                    {doc.extraction_status === "done" && doc.extracted_items > 0 && (
                      <span className="text-ok text-xs">
                        +{doc.extracted_items} item{doc.extracted_items > 1 ? "s" : ""}
                      </span>
                    )}
                    <div className="flex items-center gap-1.5">
                      {STATUS_ICON[doc.extraction_status]}
                      <Badge variant={STATUS_BADGE[doc.extraction_status]}>
                        {doc.extraction_status}
                      </Badge>
                    </div>
                  </div>
                </div>

                {/* Extraction message */}
                {doc.extraction_status === "processing" && (
                  <div className="mt-3 flex items-center gap-2 text-info text-xs bg-info/5 rounded-lg px-3 py-2">
                    <RefreshCw size={12} className="animate-spin" />
                    Analysing document with AI — this may take a few seconds...
                  </div>
                )}
                {doc.extraction_status === "done" && doc.extracted_items === 0 && (
                  <p className="mt-2 text-slate-500 text-xs">
                    No academic items detected in this document.
                  </p>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* How it works */}
      <Card className="mt-8 bg-black/40 backdrop-blur-md">
        <h3 className="text-paper font-display font-semibold mb-3">How it works</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-slate-400">
          <div className="flex items-start gap-3">
            <span className="text-emerald-500 font-display font-bold text-lg">1</span>
            <div>
              <p className="text-white text-xs font-medium">Upload</p>
              <p className="text-xs mt-1">Upload a PDF (syllabus, notice) or image (screenshot of WhatsApp/email)</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-emerald-500 font-display font-bold text-lg">2</span>
            <div>
              <p className="text-white text-xs font-medium">Extract</p>
              <p className="text-xs mt-1">spaCy NLP + Tesseract OCR extract subject, type, and deadline from text</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-emerald-500 font-display font-bold text-lg">3</span>
            <div>
              <p className="text-white text-xs font-medium">Auto-create</p>
              <p className="text-xs mt-1">Extracted items are saved to your Assignments list automatically</p>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
