import React, { useState, useRef } from "react";

interface UploadPanelProps {
  onUpload: (file: File) => void;
  onDemo: () => void;
  isLoading: boolean;
}

const ACCEPTED_FORMATS = [
  "audio/wav",
  "audio/mpeg",
  "audio/mp3",
  "audio/ogg",
  "audio/flac",
  "audio/webm",
  "video/mp4",
  "video/webm",
  "video/ogg",
];

/**
 * Upload panel for audio/video files with drag-and-drop support.
 * Also provides a "Run Demo" button for testing without a file.
 */
export default function UploadPanel({ onUpload, onDemo, isLoading }: UploadPanelProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleSubmit = () => {
    if (selectedFile) {
      onUpload(selectedFile);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`
          border-2 border-dashed rounded-xl p-8 text-center cursor-pointer
          transition-all duration-200
          ${isDragging
            ? "border-blue-500 bg-blue-950/20"
            : "border-gray-700 hover:border-gray-600 hover:bg-gray-900/50"
          }
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_FORMATS.join(",")}
          onChange={handleFileSelect}
          className="hidden"
        />

        <svg
          className="w-12 h-12 mx-auto mb-3 text-gray-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>

        <p className="text-sm text-gray-400 mb-1">
          {isDragging
            ? "Drop your file here"
            : "Drag & drop an audio/video file, or click to browse"}
        </p>
        <p className="text-xs text-gray-600">
          Supports WAV, MP3, OGG, FLAC, WebM, MP4
        </p>
      </div>

      {/* Selected file info */}
      {selectedFile && (
        <div className="flex items-center justify-between bg-gray-900 rounded-lg p-3">
          <div className="flex items-center gap-3">
            <svg
              className="w-8 h-8 text-blue-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
              />
            </svg>
            <div>
              <p className="text-sm text-gray-200 font-medium">
                {selectedFile.name}
              </p>
              <p className="text-xs text-gray-500">
                {formatFileSize(selectedFile.size)}
              </p>
            </div>
          </div>
          <button
            onClick={() => setSelectedFile(null)}
            className="text-gray-500 hover:text-gray-300"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleSubmit}
          disabled={!selectedFile || isLoading}
          className={`
            flex-1 py-2.5 px-4 rounded-lg font-medium text-sm transition-all
            ${selectedFile && !isLoading
              ? "bg-blue-600 hover:bg-blue-700 text-white"
              : "bg-gray-800 text-gray-500 cursor-not-allowed"
            }
          `}
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Analyzing...
            </span>
          ) : (
            "Analyze"
          )}
        </button>

        <button
          onClick={onDemo}
          disabled={isLoading}
          className={`
            py-2.5 px-4 rounded-lg font-medium text-sm transition-all
            ${isLoading
              ? "bg-gray-800 text-gray-500 cursor-not-allowed"
              : "bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700"
            }
          `}
        >
          ⚡ Demo
        </button>
      </div>
    </div>
  );
}
