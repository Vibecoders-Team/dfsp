import {Routes, Route, Navigate} from "react-router-dom";
import Home from "../pages/Home";
import HealthPage from "../pages/HealthPage";
import Upload from "../pages/Upload";
import Files from "../pages/Files";
import Verify from "../pages/Verify";
import LoginPage from "../pages/Login";
import RegisterPage from "../pages/Register";
import FileDetails from "../pages/FileDetails"; 
import DownloadCap from "../pages/DownloadCap";



export function AppRoutes() {
    return (
        <Routes>
            <Route path="/" element={<Home/>}/>
            <Route path="/health" element={<HealthPage/>}/>
            <Route path="/upload" element={<Upload/>}/>
            <Route path="/files" element={<Files/>}/>
            <Route path="/verify" element={<Verify/>}/>
            <Route path="/login" element={<LoginPage/>}/>
            <Route path="/register" element={<RegisterPage/>}/>
            <Route path="*" element={<Navigate to="/" replace/>}/>
            <Route path="/files/:fileId" element={<FileDetails />}/>
            <Route path="/download/:capId" element={<DownloadCap />} />
            <Route path="/d/:capId" element={<DownloadCap />} />
        </Routes>
    );
}

export default AppRoutes;
