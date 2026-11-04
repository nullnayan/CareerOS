"use client";

import React, { createContext, useContext, useState, ReactNode, useCallback } from "react";
import { uploadResume, analyzeATS, ATSResult } from "../lib/api";

interface TaskContextType {
  // Resume upload state
  uploading: boolean;
  uploadResult: any;
  uploadError: string | null;
  uploadFile: File | null;
  setUploadFile: (file: File | null) => void;
  startUpload: (file: File, source?: string) => Promise<any>;
  resetUpload: () => void;

  // ATS analysis state
  analyzing: boolean;
  atsResult: ATSResult | null;
  setAtsResult: React.Dispatch<React.SetStateAction<ATSResult | null>>;
  atsError: string | null;
  setAtsError: (err: string | null) => void;
  selectedResumeId: string;
  setSelectedResumeId: (id: string) => void;
  jobDescription: string;
  setJobDescription: (jd: string) => void;
  startATSAnalysis: (resumeId: string, jd?: string) => Promise<ATSResult>;
  resetATSAnalysis: () => void;
}

const TaskContext = createContext<TaskContextType | undefined>(undefined);

export function TaskProvider({ children }: { children: ReactNode }) {
  // Upload states
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // ATS states
  const [analyzing, setAnalyzing] = useState(false);
  const [atsResult, setAtsResult] = useState<ATSResult | null>(null);
  const [atsError, setAtsError] = useState<string | null>(null);
  const [selectedResumeId, setSelectedResumeId] = useState<string>("");
  const [jobDescription, setJobDescription] = useState<string>("");

  const startUpload = useCallback(async (file: File, source: string = "uploaded") => {
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      const res = await uploadResume(file, source);
      setUploadResult(res);
      setUploadFile(null);
      return res;
    } catch (err: any) {
      setUploadError(err.message || "Upload failed.");
      throw err;
    } finally {
      setUploading(false);
    }
  }, []);

  const resetUpload = useCallback(() => {
    setUploading(false);
    setUploadResult(null);
    setUploadError(null);
    setUploadFile(null);
  }, []);

  const startATSAnalysis = useCallback(async (resumeId: string, jd?: string) => {
    setAnalyzing(true);
    setAtsError(null);
    setAtsResult(null);
    try {
      const res = await analyzeATS(resumeId, jd);
      setAtsResult(res);
      return res;
    } catch (err: any) {
      setAtsError(err.message || "Analysis failed.");
      throw err;
    } finally {
      setAnalyzing(false);
    }
  }, []);

  const resetATSAnalysis = useCallback(() => {
    setAnalyzing(false);
    setAtsResult(null);
    setAtsError(null);
  }, []);

  return (
    <TaskContext.Provider
      value={{
        uploading,
        uploadResult,
        uploadError,
        uploadFile,
        setUploadFile,
        startUpload,
        resetUpload,

        analyzing,
        atsResult,
        setAtsResult,
        atsError,
        setAtsError,
        selectedResumeId,
        setSelectedResumeId,
        jobDescription,
        setJobDescription,
        startATSAnalysis,
        resetATSAnalysis,
      }}
    >
      {children}
    </TaskContext.Provider>
  );
}

export function useTasks() {
  const context = useContext(TaskContext);
  if (context === undefined) {
    throw new Error("useTasks must be used within a TaskProvider");
  }
  return context;
}
