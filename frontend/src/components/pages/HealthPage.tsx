import { useState, useEffect } from 'react';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { CheckCircle2, XCircle, AlertCircle, RefreshCw, Database, Server, Link as LinkIcon, Box } from 'lucide-react';

type ServiceStatus = 'ok' | 'failed' | 'degraded';
import type * as React from "react";

interface ServiceCheck {
  name: string;
  status: ServiceStatus;
  message: string;
  icon: React.ReactNode;
  responseTime?: number;
}

export default function HealthPage() {
  const [overallStatus, setOverallStatus] = useState<'loading' | 'ok' | 'partial' | 'failed'>('loading');
  const [services, setServices] = useState<ServiceCheck[]>([]);
  const [lastChecked, setLastChecked] = useState<Date>(new Date());

  const checkHealth = async () => {
    setOverallStatus('loading');

    // Simulate health checks
    await new Promise(resolve => setTimeout(resolve, 1500));

    const mockServices: ServiceCheck[] = [
      {
        name: 'Database',
        status: 'ok',
        message: 'PostgreSQL is responding normally',
        icon: <Database className="h-5 w-5" />,
        responseTime: 12
      },
      {
        name: 'Redis Cache',
        status: 'ok',
        message: 'Redis is operational',
        icon: <Server className="h-5 w-5" />,
        responseTime: 3
      },
      {
        name: 'Blockchain Node',
        status: 'ok',
        message: 'Connected to Ethereum mainnet (block 18234567)',
        icon: <LinkIcon className="h-5 w-5" />,
        responseTime: 145
      },
      {
        name: 'Message Queues',
        status: 'ok',
        message: 'All queues are processing normally',
        icon: <Box className="h-5 w-5" />,
        responseTime: 8
      },
      {
        name: 'IPFS Gateway',
        status: 'ok',
        message: 'IPFS gateway is accessible and syncing',
        icon: <Box className="h-5 w-5" />,
        responseTime: 234
      }
    ];

    setServices(mockServices);

    // Determine overall status
    const failedServices = mockServices.filter(s => s.status === 'failed');
    const degradedServices = mockServices.filter(s => s.status === 'degraded');

    if (failedServices.length > 0) {
      setOverallStatus('failed');
    } else if (degradedServices.length > 0) {
      setOverallStatus('partial');
    } else {
      setOverallStatus('ok');
    }

    setLastChecked(new Date());
  };

  useEffect(() => {
    checkHealth();
  }, []);

  const getStatusIcon = (status: ServiceStatus) => {
    switch (status) {
      case 'ok':
        return <CheckCircle2 className="h-5 w-5 text-green-600" />;
      case 'degraded':
        return <AlertCircle className="h-5 w-5 text-yellow-600" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-600" />;
    }
  };

  const getStatusBadge = (status: ServiceStatus) => {
    switch (status) {
      case 'ok':
        return <Badge className="bg-green-100 text-green-800">OK</Badge>;
      case 'degraded':
        return <Badge className="bg-yellow-100 text-yellow-800">Degraded</Badge>;
      case 'failed':
        return <Badge variant="destructive">Failed</Badge>;
    }
  };

  const getOverallStatusColor = () => {
    switch (overallStatus) {
      case 'ok':
        return 'text-green-600';
      case 'partial':
        return 'text-yellow-600';
      case 'failed':
        return 'text-red-600';
      default:
        return 'text-gray-600';
    }
  };

  const getOverallStatusText = () => {
    switch (overallStatus) {
      case 'loading':
        return 'Checking system health...';
      case 'ok':
        return 'All systems operational';
      case 'partial':
        return 'Some services degraded';
      case 'failed':
        return 'System issues detected';
    }
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <Layout>
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1>System Health</h1>
            <p className="text-gray-600">Monitor the status of all system components</p>
          </div>
          <Button
            onClick={checkHealth}
            disabled={overallStatus === 'loading'}
            variant="outline"
            className="gap-2"
          >
            <RefreshCw className={`h-4 w-4 ${overallStatus === 'loading' ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>

        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 mb-4">
                {overallStatus === 'loading' ? (
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
                ) : (
                  getStatusIcon(overallStatus === 'ok' ? 'ok' : overallStatus === 'partial' ? 'degraded' : 'failed')
                )}
              </div>
              <h2 className={getOverallStatusColor()}>{getOverallStatusText()}</h2>
              <p className="text-sm text-gray-500 mt-2">
                Last checked: {formatTime(lastChecked)}
              </p>
            </div>
          </CardContent>
        </Card>

        {overallStatus !== 'loading' && (
          <div className="space-y-4">
            {services.map((service, index) => (
              <Card key={index}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="text-gray-600">
                        {service.icon}
                      </div>
                      <CardTitle className="text-lg">{service.name}</CardTitle>
                    </div>
                    {getStatusBadge(service.status)}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {getStatusIcon(service.status)}
                      <span className="text-sm text-gray-600">{service.message}</span>
                    </div>
                    {service.responseTime !== undefined && (
                      <span className="text-xs text-gray-500">
                        {service.responseTime}ms
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Additional Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-600">Environment</span>
                <span>Production</span>
              </div>
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-600">Version</span>
                <span>1.0.0</span>
              </div>
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-600">Uptime</span>
                <span>99.9%</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-gray-600">API Status</span>
                <a href={window.location.origin + '/health'} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                  View Details
                </a>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
